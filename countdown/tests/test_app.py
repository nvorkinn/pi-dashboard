import asyncio
import logging
from importlib.metadata import entry_points
from types import SimpleNamespace

import pytest
import requests
from config_factory import make_config
from pydantic import BaseModel, ValidationError

from countdown_core.config_server.models import AppConfig
from countdown_core.core import app
from countdown_core.core.display_loop import safe_fetch
from countdown_credentials.registration import RendererRegistrar, RendererRegistration
from countdown_standalone import main as standalone_main


def test_safe_fetch_returns_func_result_on_success():
    assert safe_fetch(lambda: 42, fallback="fallback") == 42


def test_safe_fetch_returns_fallback_on_request_exception():
    def boom():
        raise requests.exceptions.ConnectionError("network down")

    assert safe_fetch(boom, fallback="fallback") == "fallback"


def test_safe_fetch_returns_fallback_on_validation_error():
    class Model(BaseModel):
        value: int

    def boom():
        Model.model_validate({"value": "not-an-int"})

    assert safe_fetch(boom, fallback="fallback") == "fallback"


def test_the_console_script_entry_point_actually_runs_the_app(monkeypatch):
    """The `countdown-standalone` script just calls main() without awaiting it, so main() must
    run the app itself. Every other test drives run() directly and wouldn't notice."""
    ran = []

    async def fake_run(make_target, standalone):
        ran.append((make_target, standalone))

    monkeypatch.setattr(app, "run", fake_run)
    # Keep the test run's own logging set-up as it is.
    monkeypatch.setattr(app, "configure_logging", lambda: None)
    panel = object()
    monkeypatch.setattr(standalone_main, "target_from_env", lambda: panel)
    (entry_point,) = entry_points(group="console_scripts", name="countdown-standalone")

    assert entry_point.load()() is None
    [(make_target, standalone)] = ran
    assert standalone is True  # the Pi is its own screen
    # The panel's target, not countdown_core's preview-only default.
    assert make_target(None) is panel


@pytest.mark.parametrize(
    ("env", "expected"), [(None, logging.INFO), ("debug", logging.DEBUG), ("nonsense", logging.INFO)]
)
def test_logging_defaults_to_info_and_honours_log_level(monkeypatch, env, expected):
    calls = []
    monkeypatch.setattr(app.logging, "basicConfig", lambda **kwargs: calls.append(kwargs))
    if env is None:
        monkeypatch.delenv("LOG_LEVEL", raising=False)
    else:
        monkeypatch.setenv("LOG_LEVEL", env)

    app.configure_logging()

    (kwargs,) = calls
    assert kwargs["level"] == expected
    assert "%(filename)s:%(lineno)d" in kwargs["format"]
    assert "asctime" not in kwargs["format"]  # journald timestamps each line itself


# --- waiting for a config at boot ---------------------------------------------------


class FakeBroker:
    """Stands in for BrokerClient: `fetch_failures` are the exceptions to raise, in order,
    before it starts succeeding."""

    def __init__(self, fetch_failures=()):
        self.fetch_failures = list(fetch_failures)
        self.fetch_calls = 0

    def fetch_app_config(self):
        self.fetch_calls += 1
        if self.fetch_failures:
            raise self.fetch_failures.pop(0)
        return make_config(), "the pairing panel"


def wait(broker):
    delays: list[float] = []
    waits = []

    async def sleep(seconds):
        delays.append(seconds)
        assert len(delays) < 50, "wait_for_config is retrying forever"

    async def on_retry():
        waits.append(len(delays))

    result = asyncio.run(app.wait_for_config(broker, sleep=sleep, on_retry=on_retry))
    return result, delays, waits


def test_a_broker_that_answers_straight_away_means_no_waiting():
    (config, panel), delays, waits = wait(FakeBroker())

    assert config == make_config()
    assert panel == "the pairing panel"
    assert delays == []
    assert waits == []


def test_an_unreachable_broker_is_retried_with_backoff():
    broker = FakeBroker(fetch_failures=[requests.exceptions.ConnectionError("down")] * 3)

    (config, _), delays, waits = wait(broker)

    assert config == make_config()
    assert delays == [30, 60, 120]
    assert waits == [0, 1, 2]  # on_retry before every sleep
    assert broker.fetch_calls == 4


def test_the_backoff_stops_growing_at_the_maximum():
    broker = FakeBroker(fetch_failures=[requests.exceptions.ConnectionError("down")] * 8)

    _, delays, _ = wait(broker)

    assert delays == [30, 60, 120, 240, 300, 300, 300, 300]


def test_a_response_that_is_not_a_valid_config_is_treated_like_no_response():
    with pytest.raises(ValidationError) as error:
        AppConfig.model_validate({})
    broker = FakeBroker(fetch_failures=[error.value])

    (config, _), delays, _ = wait(broker)

    assert config == make_config()
    assert delays == [30]


def test_a_real_bug_still_crashes_loudly_instead_of_being_retried_forever():
    broker = FakeBroker(fetch_failures=[TypeError("a bug")])

    with pytest.raises(TypeError):
        wait(broker)


# --- run() ----------------------------------------------------------------------------

REGISTRATION = RendererRegistration("https://broker.example.com", "shh", "device-123")


@pytest.fixture
def booted(monkeypatch):
    """Runs app.run() with the registration and everything after it faked, recording what it did."""
    monkeypatch.setenv("BROKER_URL", "https://broker.example.com")
    seen = {"order": []}

    class FakeLoop:
        def __init__(self, broker, config, pairing_code_panel, display, registry):
            seen.update(broker=broker, display=display, registry=registry)

        async def run(self):
            seen["order"].append("loop")

    async def fake_register(registrar):
        seen["order"].append("register")
        seen["registrar"] = registrar
        return REGISTRATION

    async def fake_wait(broker, on_retry=None):
        seen["order"].append("config")
        seen["on_retry"] = on_retry
        return make_config(), "the pairing panel"

    def make_target(registration):
        seen["order"].append("target")
        seen["target_registration"] = registration
        return "the target"

    fake_display = SimpleNamespace(panel_connected=True, shutdown=lambda: None)
    monkeypatch.setattr(RendererRegistrar, "register", fake_register)
    monkeypatch.setattr(app, "DisplayController", lambda target: seen.update(target=target) or fake_display)
    monkeypatch.setattr(app, "DisplayLoop", FakeLoop)
    monkeypatch.setattr(app, "wait_for_config", fake_wait)
    monkeypatch.setattr(app.signal, "signal", lambda *args: None)

    def boot(standalone=True):
        asyncio.run(app.run(make_target, standalone=standalone))
        return seen

    return boot


def test_run_does_nothing_until_the_device_is_registered(booted):
    seen = booted()

    assert seen["order"] == ["register", "target", "config", "loop"]


@pytest.mark.parametrize("standalone", [True, False])
def test_run_registers_as_a_standalone_or_split_renderer(booted, standalone):
    registrar = booted(standalone=standalone)["registrar"]

    assert registrar.broker_url == "https://broker.example.com"
    assert registrar.standalone is standalone


def test_run_shares_the_one_registration_between_the_target_the_broker_and_the_registry(booted):
    seen = booted()

    assert seen["target_registration"] is REGISTRATION
    assert seen["target"] == "the target"
    assert seen["broker"].registration is REGISTRATION
    assert seen["registry"].registration is REGISTRATION


def test_run_wires_one_device_status_through_the_registry_the_config_wait_and_the_loop(booted):
    seen = booted()

    registry = seen["registry"]
    assert registry.status.display is seen["display"]
    assert seen["on_retry"] == registry.publish_health
    assert registry.status.last_broker_sync is not None
