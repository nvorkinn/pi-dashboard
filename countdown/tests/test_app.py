import asyncio
import logging
from importlib.metadata import entry_points
from types import SimpleNamespace

import pytest
import requests
from config_factory import make_config
from pydantic import BaseModel, ValidationError

from countdown import app
from countdown.config_server.config_manager import AppConfig
from countdown.core.abstract_client import ClientStatus
from countdown.core.display_loop import safe_fetch


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
    """The `countdown` script just calls main() without awaiting it, so main() must run the
    app itself. Every other test drives run() directly and wouldn't notice."""
    ran = []

    async def fake_run():
        ran.append(True)

    monkeypatch.setattr(app, "run", fake_run)
    # Keep the test run's own logging set-up as it is.
    monkeypatch.setattr(app, "configure_logging", lambda: None)
    (entry_point,) = entry_points(group="console_scripts", name="countdown")

    assert entry_point.load()() is None
    assert ran == [True]


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


# --- waiting for a config at boot ----------------------------------------------------


class FakeBroker:
    """Stands in for BrokerClient: `initialise_failures` and `fetch_failures` are the
    exceptions to raise, in order, before it starts succeeding."""

    def __init__(self, initialise_failures=(), fetch_failures=()):
        self.initialise_failures = list(initialise_failures)
        self.fetch_failures = list(fetch_failures)
        self.status = ClientStatus.UNINITIALISED
        self.initialise_calls = 0
        self.fetch_calls = 0

    async def initialise(self):
        self.initialise_calls += 1
        if self.initialise_failures:
            self.status = ClientStatus.ERROR
            raise self.initialise_failures.pop(0)
        self.status = ClientStatus.CONNECTED

    def fetch_app_config(self):
        self.fetch_calls += 1
        if self.fetch_failures:
            raise self.fetch_failures.pop(0)
        return make_config(), "the pairing panel"


class FakeDisplay:
    def __init__(self):
        self.splashes = []

    def display_splash(self, panel):
        self.splashes.append(type(panel).__name__)


def wait(broker, display=None, on_retry=None):
    display = display or FakeDisplay()
    delays: list[float] = []

    async def sleep(seconds):
        delays.append(seconds)
        assert len(delays) < 50, "wait_for_config is retrying forever"

    result = asyncio.run(app.wait_for_config(broker, display, sleep=sleep, on_retry=on_retry))
    return result, display, delays


def test_a_broker_that_answers_straight_away_means_no_splash_and_no_waiting():
    (config, panel), display, delays = wait(FakeBroker())

    assert config == make_config()
    assert panel == "the pairing panel"
    assert display.splashes == []
    assert delays == []


def test_an_unreachable_broker_shows_the_splash_once_and_retries_with_backoff():
    broker = FakeBroker(fetch_failures=[requests.exceptions.ConnectionError("down")] * 3)

    (config, _), display, delays = wait(broker)

    assert config == make_config()
    assert display.splashes == ["SplashPanel"]  # painted once, not on every retry
    assert delays == [30, 60, 120]
    assert broker.fetch_calls == 4


def test_the_backoff_stops_growing_at_the_maximum():
    broker = FakeBroker(fetch_failures=[requests.exceptions.ConnectionError("down")] * 8)

    _, _, delays = wait(broker)

    assert delays == [30, 60, 120, 240, 300, 300, 300, 300]


def test_a_response_that_is_not_a_valid_config_is_treated_like_no_response():
    with pytest.raises(ValidationError) as error:
        AppConfig.model_validate({})
    broker = FakeBroker(fetch_failures=[error.value])

    (config, _), display, delays = wait(broker)

    assert config == make_config()
    assert display.splashes == ["SplashPanel"]
    assert delays == [30]


def test_a_failed_first_time_registration_is_retried_instead_of_crashing():
    broker = FakeBroker(initialise_failures=[requests.exceptions.ConnectionError("down")])

    _, display, delays = wait(broker)

    assert display.splashes == ["SplashPanel"]
    assert delays == [30]
    assert broker.initialise_calls == 2


def test_once_registered_a_failing_config_fetch_does_not_register_again():
    broker = FakeBroker(fetch_failures=[requests.exceptions.ConnectionError("down")])

    wait(broker)

    assert broker.initialise_calls == 1


def test_a_real_bug_still_crashes_loudly_instead_of_being_retried_forever():
    broker = FakeBroker(fetch_failures=[TypeError("a bug")])

    with pytest.raises(TypeError):
        wait(broker)


def test_the_wait_reports_each_failed_attempt_through_on_retry():
    broker = FakeBroker(fetch_failures=[requests.exceptions.ConnectionError("down")] * 3)
    reported = []

    async def on_retry():
        reported.append(1)

    wait(broker, on_retry=on_retry)

    assert len(reported) == 3


def test_a_broker_that_answers_straight_away_reports_nothing():
    reported = []

    async def on_retry():
        reported.append(1)

    wait(FakeBroker(), on_retry=on_retry)

    assert reported == []


def test_run_wires_one_device_status_through_the_registry_the_boot_wait_and_the_loop(monkeypatch):
    monkeypatch.setenv("BROKER_URL", "https://broker.example.com")
    seen = {}

    class FakeLoop:
        def __init__(self, broker, config, pairing_code_panel, display, registry):
            seen.update(display=display, registry=registry)

        async def run(self):
            pass

    async def fake_wait(broker, display, on_retry=None):
        seen["on_retry"] = on_retry
        return make_config(), "the pairing panel"

    fake_display = SimpleNamespace(panel_connected=True, shutdown=lambda: None)
    monkeypatch.setattr(app, "BrokerClient", lambda url: object())
    monkeypatch.setattr(app, "DisplayController", lambda: fake_display)
    monkeypatch.setattr(app, "DisplayLoop", FakeLoop)
    monkeypatch.setattr(app, "wait_for_config", fake_wait)
    monkeypatch.setattr(app.signal, "signal", lambda *args: None)

    asyncio.run(app.run())

    registry = seen["registry"]
    assert seen["display"] is fake_display
    assert registry.status.display is fake_display
    assert seen["on_retry"] == registry.publish_health
    assert registry.status.last_broker_sync is not None
