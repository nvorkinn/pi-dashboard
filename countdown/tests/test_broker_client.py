import asyncio
import json
from unittest.mock import MagicMock

import pytest
import requests
import responses
from pydantic import ValidationError

from countdown.config_server import broker_client as broker_client_module
from countdown.config_server.broker_client import CREDENTIALS_FILE, BrokerClient
from countdown.config_server.config_manager import AppConfig

BROKER_URL = "https://broker.example.com"
DEFAULT_TIMEOUT = 10


def _app_config(pairing_code: str | None) -> AppConfig:
    return AppConfig(
        interval=15,
        tfl={"app_key": "", "stop_ids": []},
        weather={"api_key": "", "location": ""},
        spotify={"enabled": False},
        glowmarkt={"username": None, "password": None},
        pairing_code=pairing_code,
        setup_missing=[],
    )


def _response(json_data: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = json_data
    return response


def _seed_credentials(device_id: str = "device-123", device_secret: str = "shh") -> None:
    CREDENTIALS_FILE.write_text(json.dumps({"device_id": device_id, "device_secret": device_secret}))


def _initialised_client() -> BrokerClient:
    """A client with credentials loaded from a seeded file (so no registration call)."""
    client = BrokerClient(BROKER_URL)
    asyncio.run(client.initialise())
    return client


def test_construction_makes_no_requests_and_loads_no_credentials(isolated_cwd):
    _seed_credentials()

    client = BrokerClient(BROKER_URL)

    assert not hasattr(client, "device_id")  # credentials are loaded by initialise(), not __init__


def test_registers_and_persists_credentials_on_first_run(isolated_cwd, monkeypatch):
    register_response = _response({"device_id": "device-123"})
    post_mock = MagicMock(return_value=register_response)

    # Patch the session before construction (_build_retrying_session() creates a fresh
    # session each time), at the spot AbstractClient.__init__ actually calls it.
    monkeypatch.setattr(
        "countdown.core.abstract_client.AbstractClient._build_retrying_session",
        staticmethod(lambda: MagicMock(post=post_mock)),
    )

    client = BrokerClient(BROKER_URL)
    asyncio.run(client.initialise())  # registration happens here, not in __init__

    assert client.device_id == "device-123"
    post_mock.assert_called_once()
    assert post_mock.call_args.kwargs["json"]["device_secret"] == client.device_secret
    assert post_mock.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT

    saved = json.loads(CREDENTIALS_FILE.read_text())
    assert saved == {"device_id": "device-123", "device_secret": client.device_secret}


def test_reuses_credentials_file_without_registering_again(isolated_cwd):
    _seed_credentials("existing-device", "existing-secret")

    client = _initialised_client()

    assert client.device_id == "existing-device"
    assert client.device_secret == "existing-secret"


def test_request_sends_bearer_auth_header(isolated_cwd):
    _seed_credentials()
    client = _initialised_client()

    response = _response({"ok": True})
    request_mock = MagicMock(return_value=response)
    client.session.request = request_mock

    result = client._request("GET", "/some/path")

    assert result == {"ok": True}
    assert request_mock.call_args.kwargs["headers"]["Authorization"] == "Bearer shh"
    assert request_mock.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT


def test_request_sends_device_name_header_from_device_id_env(isolated_cwd, monkeypatch):
    monkeypatch.setenv("DEVICE_ID", "Sister HAT")
    _seed_credentials()
    client = _initialised_client()
    request_mock = MagicMock(return_value=_response({}))
    client.session.request = request_mock

    client._request("GET", "/some/path")

    assert request_mock.call_args.kwargs["headers"]["X-Device-Name"] == "sister-hat"


def test_request_sends_device_name_header_from_hostname_when_device_id_unset(isolated_cwd, monkeypatch):
    monkeypatch.setattr(broker_client_module.socket, "gethostname", lambda: "vorkin-rbpi-z2w")
    _seed_credentials()
    client = _initialised_client()
    request_mock = MagicMock(return_value=_response({}))
    client.session.request = request_mock

    client._request("GET", "/some/path")

    assert request_mock.call_args.kwargs["headers"]["X-Device-Name"] == "vorkin-rbpi-z2w"


def test_request_omits_device_name_header_when_unresolvable(isolated_cwd, monkeypatch):
    """Never allowed to fail the request itself -- a dev box with an unresolvable
    hostname and no DEVICE_ID just doesn't send the (purely cosmetic) header."""
    monkeypatch.setattr(broker_client_module.socket, "gethostname", lambda: "")
    _seed_credentials()
    client = _initialised_client()
    request_mock = MagicMock(return_value=_response({}))
    client.session.request = request_mock

    client._request("GET", "/some/path")

    assert "X-Device-Name" not in request_mock.call_args.kwargs["headers"]


def test_get_config_parses_response(isolated_cwd):
    _seed_credentials()
    client = _initialised_client()
    client.session.request = MagicMock(
        return_value=_response(
            {
                "interval": 20,
                "tfl": {"app_key": "tfl-key", "stop_ids": ["940GZZLUEUS"]},
                "weather": {"api_key": "weather-key", "location": "London"},
                "spotify": {"enabled": True},
                "glowmarkt": {"username": "me@example.com", "password": "hunter2"},
                "pairing_code": None,
                "setup_missing": [],
            }
        )
    )

    config = client.get_config()

    assert config.interval == 20
    assert config.tfl.stop_ids == ["940GZZLUEUS"]
    assert config.spotify.enabled is True
    assert config.glowmarkt.username == "me@example.com"
    assert config.pairing_code is None


def test_get_config_accepts_null_glowmarkt_credentials(isolated_cwd):
    """The common case: a device whose owner hasn't set up Glowmarkt on the
    broker. Sent as null, not omitted -- must parse, not raise."""
    _seed_credentials()
    client = _initialised_client()
    client.session.request = MagicMock(
        return_value=_response(
            {
                "interval": 15,
                "tfl": {"app_key": "", "stop_ids": []},
                "weather": {"api_key": "", "location": ""},
                "spotify": {"enabled": False},
                "glowmarkt": {"username": None, "password": None},
                "pairing_code": "ABC123",
                "setup_missing": [],
            }
        )
    )

    config = client.get_config()

    assert config.glowmarkt.username is None
    assert config.glowmarkt.password is None
    assert config.pairing_code == "ABC123"


def test_get_pairing_code_panel_wraps_code_and_device_id(isolated_cwd):
    _seed_credentials()
    client = _initialised_client()

    panel = client.get_pairing_code_panel(_app_config("ABC123"))

    assert panel.pairing_code == "ABC123"
    assert panel.device_id == "device-123"


def test_get_pairing_code_panel_has_changed_false_on_repeat(isolated_cwd):
    """A paired device gets `pairing_code=None` on every poll; has_changed must stay False."""
    _seed_credentials()
    client = _initialised_client()

    first = client.get_pairing_code_panel(_app_config(None))
    second = client.get_pairing_code_panel(_app_config(None))

    assert first.has_changed is True  # first time this endpoint's been seen at all
    assert second.has_changed is False


def test_get_pairing_code_panel_has_changed_true_when_code_changes(isolated_cwd):
    _seed_credentials()
    client = _initialised_client()

    client.get_pairing_code_panel(_app_config("ABC123"))
    regenerated = client.get_pairing_code_panel(_app_config("XYZ789"))
    now_paired = client.get_pairing_code_panel(_app_config(None))

    assert regenerated.has_changed is True
    assert now_paired.has_changed is True


@responses.activate
def test_fetch_app_config_uses_real_broker_response(isolated_cwd):
    _seed_credentials("test-device", "test-secret")
    client = _initialised_client()
    responses.add(
        responses.GET,
        f"{BROKER_URL}/api/devices/test-device/config",
        json={
            "interval": 20,
            "tfl": {"app_key": "tfl-key", "stop_ids": ["940GZZLUEUS"]},
            "weather": {"api_key": "weather-key", "location": "London"},
            "spotify": {"enabled": True},
            "glowmarkt": {"username": None, "password": None},
            "pairing_code": "XYZ789",
            "setup_missing": [],
        },
    )

    config, pairing_code_panel = client.fetch_app_config()

    assert config.interval == 20
    assert config.tfl.stop_ids == ["940GZZLUEUS"]
    assert config.spotify.enabled is True
    assert pairing_code_panel.pairing_code == "XYZ789"
    assert pairing_code_panel.device_id == "test-device"
    assert pairing_code_panel.has_changed is True  # first time this device's ever checked


@responses.activate
def test_fetch_app_config_raises_when_broker_unreachable(isolated_cwd):
    """No empty fallback: with no config there's nothing sensible to run, so the caller
    (app.wait_for_config) shows a splash and retries."""
    _seed_credentials("test-device", "test-secret")
    client = _initialised_client()
    # /config deliberately left unmocked -- responses raises ConnectionError for it.

    with pytest.raises(requests.exceptions.ConnectionError):
        client.fetch_app_config()


@responses.activate
def test_fetch_app_config_raises_when_response_is_invalid(isolated_cwd):
    _seed_credentials("test-device", "test-secret")
    client = _initialised_client()
    responses.add(responses.GET, f"{BROKER_URL}/api/devices/test-device/config", json={"interval": "soon"})

    with pytest.raises(ValidationError):
        client.fetch_app_config()


@responses.activate
def test_a_failed_fetch_does_not_mark_the_pairing_code_as_seen(isolated_cwd):
    """The first *successful* fetch is still the one that reports has_changed."""
    _seed_credentials("test-device", "test-secret")
    client = _initialised_client()
    with pytest.raises(requests.exceptions.ConnectionError):
        client.fetch_app_config()
    responses.add(
        responses.GET,
        f"{BROKER_URL}/api/devices/test-device/config",
        json=_app_config("ABC123").model_dump(),
    )

    _, pairing_code_panel = client.fetch_app_config()

    assert pairing_code_panel.pairing_code == "ABC123"
    assert pairing_code_panel.has_changed is True
