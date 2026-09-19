import asyncio
import json
from unittest.mock import MagicMock

import responses

from countdown.broker_client import CREDENTIALS_FILE, BrokerClient
from countdown.config_manager import AppConfig
from countdown.http import DEFAULT_TIMEOUT

BROKER_URL = "https://broker.example.com"


def _app_config(pairing_code: str | None) -> AppConfig:
    return AppConfig(
        interval=15,
        tfl={"app_key": "", "stop_ids": []},
        weather={"api_key": "", "location": ""},
        spotify={"enabled": False},
        glowmarkt={"username": None, "password": None},
        pairing_code=pairing_code,
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

    # Patch the session before construction (build_retrying_session() creates a fresh
    # session each time), at the spot AbstractClient.__init__ actually calls it.
    monkeypatch.setattr("countdown.abstract_client.build_retrying_session", lambda: MagicMock(post=post_mock))

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
    """A device that's already paired gets `pairing_code=None` on every poll --
    has_changed must stay False for that steady state, not flip True forever
    just because None happens to look like "nothing cached yet" if compared
    carelessly."""
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
def test_fetch_app_config_falls_back_to_empty_when_broker_unreachable(isolated_cwd):
    _seed_credentials("test-device", "test-secret")
    client = _initialised_client()
    # /config deliberately left unmocked -- responses raises ConnectionError for it.

    config, pairing_code_panel = client.fetch_app_config()

    assert config.tfl.stop_ids == []
    assert config.interval == 15
    assert pairing_code_panel.pairing_code is None
    assert pairing_code_panel.device_id == "test-device"
    assert pairing_code_panel.has_changed is False  # nothing was fetched, so nothing to repaint


@responses.activate
def test_fetch_app_config_falls_back_to_empty_when_response_is_invalid(isolated_cwd):
    _seed_credentials("test-device", "test-secret")
    client = _initialised_client()
    responses.add(responses.GET, f"{BROKER_URL}/api/devices/test-device/config", json={"interval": "soon"})

    config, pairing_code_panel = client.fetch_app_config()

    assert config.interval == 15
    assert pairing_code_panel.pairing_code is None
