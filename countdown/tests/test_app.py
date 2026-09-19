import asyncio
from importlib.metadata import entry_points

import pytest
import requests
from config_factory import make_config
from pydantic import BaseModel, ValidationError

from countdown import app
from countdown.abstract_client import ClientStatus
from countdown.config_manager import AppConfig
from countdown.display_loop import safe_fetch


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
    """The `countdown` script just calls what pyproject.toml points at. When that was an
    `async def`, the call created a coroutine, never awaited it, and the service
    crash-looped -- while every other test, which drive run() directly, stayed green."""
    ran = []

    async def fake_run():
        ran.append(True)

    monkeypatch.setattr(app, "run", fake_run)
    (entry_point,) = entry_points(group="console_scripts", name="countdown")

    assert entry_point.load()() is None
    assert ran == [True]


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


def wait(broker, display=None):
    display = display or FakeDisplay()
    delays: list[float] = []

    async def sleep(seconds):
        delays.append(seconds)
        assert len(delays) < 50, "wait_for_config is retrying forever"

    result = asyncio.run(app.wait_for_config(broker, display, sleep=sleep))
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
