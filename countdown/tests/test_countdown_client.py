import asyncio
import json
import logging
import sys
import types
from unittest.mock import MagicMock, call

import pytest
import requests
import responses
from test_utils import Sleeps, StopWaiting

import countdown_epd
from countdown_client import client as client_module
from countdown_client import main as client_main
from countdown_client.client import Client
from countdown_credentials.registration import CREDENTIALS_FILE, DEFAULT_RETRY_S, REQUEST_TIMEOUT_S, DisplayRegistrar

BROKER_URL = "https://broker.example.com"
REGISTER_URL = f"{BROKER_URL}/api/devices/register"
FRAME_URL = f"{BROKER_URL}/api/frame"


@pytest.fixture(autouse=True)
def client_env(isolated_cwd, monkeypatch):
    monkeypatch.setenv("BROKER_URL", BROKER_URL)
    CREDENTIALS_FILE.write_text(json.dumps({"device_secret": "shh"}))


@pytest.fixture
def epd(monkeypatch):
    """Stands in for the e-paper driver, so no client test needs the hardware."""
    epd = MagicMock()
    monkeypatch.setattr(Client, "_load_epd", lambda self: setattr(self, "epd", epd))
    return epd


@pytest.fixture
def sleeps(monkeypatch) -> Sleeps:
    """One fake sleep for both the registration's waits and the poll loop's. Ends the run at the first."""
    sleeps = Sleeps(stop_after=1)
    monkeypatch.setattr(client_module.asyncio, "sleep", sleeps)
    return sleeps


@pytest.fixture
def client(epd, sleeps) -> Client:
    return Client(DisplayRegistrar(BROKER_URL, sleep=sleeps))


@pytest.fixture
def broker():
    """The broker, which accepts the client's registration."""
    with responses.RequestsMock() as rsps:
        rsps.post(REGISTER_URL, status=201)
        yield rsps


def _run(client: Client) -> None:
    with pytest.raises(StopWaiting):
        asyncio.run(client.start())


def _requests_to(broker, url: str) -> list[requests.PreparedRequest]:
    return [c.request for c in broker.calls if c.request.url == url]


# --- Construction -------------------------------------------------------------------


def test_registers_as_a_display_on_the_broker_from_the_environment(epd):
    registrar = Client().registrar

    assert isinstance(registrar, DisplayRegistrar)
    assert registrar.broker_url == BROKER_URL


def test_needs_a_broker_url(epd, monkeypatch):
    monkeypatch.delenv("BROKER_URL")

    with pytest.raises(KeyError):
        Client()


def test_builds_the_panel_from_countdown_epd(monkeypatch):
    # A fake driver: importing the real one probes the board's GPIO.
    driver = types.ModuleType("countdown_epd.epd7in5_V2")
    driver.EPD = MagicMock(name="EPD")
    monkeypatch.setitem(sys.modules, "countdown_epd.epd7in5_V2", driver)
    monkeypatch.setattr(countdown_epd, "epd7in5_V2", driver, raising=False)

    assert Client().epd is driver.EPD.return_value


# --- Polling ------------------------------------------------------------------------


def test_registers_before_polling(client, broker):
    broker.get(FRAME_URL, status=304)

    _run(client)

    assert [c.request.url for c in broker.calls] == [REGISTER_URL, FRAME_URL]


def test_polls_the_frame_as_a_display_with_the_registered_secret(client, broker):
    broker.get(FRAME_URL, status=304)

    _run(client)

    [request] = _requests_to(broker, FRAME_URL)
    assert request.method == "GET"
    assert json.loads(request.body) == {"role": "display"}
    assert request.headers["Authorization"] == "Bearer shh"
    assert request.req_kwargs["timeout"] == REQUEST_TIMEOUT_S


def test_paints_a_new_frame_and_sleeps_the_panel(client, broker, epd):
    broker.get(FRAME_URL, body=b"\x00\xff\x0f")

    _run(client)

    assert epd.mock_calls == [call.init(), call.display(bytearray(b"\x00\xff\x0f")), call.sleep()]


@pytest.mark.parametrize("status", [202, 304, 404])
def test_leaves_the_panel_alone_when_theres_nothing_new(client, broker, epd, status, caplog):
    broker.get(FRAME_URL, status=status)

    with caplog.at_level(logging.WARNING):
        _run(client)

    assert epd.mock_calls == []
    assert caplog.text == ""


def test_waits_as_long_as_the_broker_says(client, broker, sleeps):
    broker.get(FRAME_URL, status=304, headers={"Retry-After": "42"})

    _run(client)

    assert sleeps == [42]


def test_waits_the_default_without_a_retry_after(client, broker, sleeps):
    broker.get(FRAME_URL, status=304)

    _run(client)

    assert sleeps == [DEFAULT_RETRY_S]


def test_an_unauthorised_poll_registers_again_with_the_same_secret(client, broker):
    broker.get(FRAME_URL, status=401)
    broker.get(FRAME_URL, status=304)

    _run(client)

    assert [c.request.url for c in broker.calls] == [REGISTER_URL, FRAME_URL, REGISTER_URL, FRAME_URL]
    assert [json.loads(r.body)["secret"] for r in _requests_to(broker, REGISTER_URL)] == ["shh", "shh"]


def test_warns_about_an_unexpected_status_without_painting(client, broker, epd, caplog):
    broker.get(FRAME_URL, status=500)

    with caplog.at_level(logging.WARNING):
        _run(client)

    assert f"Unexpected 500 from {FRAME_URL}" in caplog.text
    assert epd.mock_calls == []


def test_keeps_polling_when_the_broker_cant_be_reached(client, broker, epd, sleeps, caplog):
    broker.get(FRAME_URL, body=requests.Timeout("read timed out"))
    broker.get(FRAME_URL, body=b"\x01")
    sleeps.stop_after = 2

    with caplog.at_level(logging.WARNING):
        _run(client)

    assert "Couldn't fetch the frame: read timed out" in caplog.text
    assert sleeps == [DEFAULT_RETRY_S, DEFAULT_RETRY_S]
    epd.display.assert_called_once_with(bytearray(b"\x01"))


# --- Entry point --------------------------------------------------------------------


def test_run_configures_logging_and_starts_the_client(mocker):
    configure_logging = mocker.patch.object(client_main, "configure_logging")
    client_cls = mocker.patch.object(client_main, "Client")
    asyncio_run = mocker.patch.object(client_main.asyncio, "run")

    client_main.run()

    configure_logging.assert_called_once_with()
    client_cls.return_value.start.assert_called_once_with()
    asyncio_run.assert_called_once_with(client_cls.return_value.start.return_value)


@pytest.mark.parametrize(
    ("log_level", "expected"), [("debug", logging.DEBUG), ("", logging.INFO), ("nope", logging.INFO)]
)
def test_log_level_comes_from_the_environment(mocker, monkeypatch, log_level, expected):
    monkeypatch.setenv("LOG_LEVEL", log_level)
    basic_config = mocker.patch.object(client_main.logging, "basicConfig")

    client_main.configure_logging()

    assert basic_config.call_args.kwargs["level"] == expected
