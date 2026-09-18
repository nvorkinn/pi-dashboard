import json
from pathlib import Path
from unittest.mock import MagicMock

from countdown.broker_client import BrokerClient, CREDENTIALS_FILE
from countdown.http import DEFAULT_TIMEOUT


def _response(json_data: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = json_data
    return response


def test_registers_and_persists_credentials_on_first_run(isolated_cwd, monkeypatch):
    register_response = _response({"device_id": "device-123"})
    pairing_response = _response({"code": "ABC123", "expires_in_seconds": 600})

    post_mock = MagicMock(return_value=register_response)
    request_mock = MagicMock(return_value=pairing_response)

    # Patch the session methods before construction, since registration happens
    # inside __init__ (build_retrying_session() creates a fresh session each time).
    monkeypatch.setattr("countdown.broker_client.build_retrying_session", lambda: MagicMock(post=post_mock, request=request_mock))

    client = BrokerClient("https://broker.example.com")

    assert client.device_id == "device-123"
    assert client.pairing_code == "ABC123"
    post_mock.assert_called_once()
    assert post_mock.call_args.kwargs["json"]["device_secret"] == client.device_secret
    assert post_mock.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT

    saved = json.loads(CREDENTIALS_FILE.read_text())
    assert saved == {"device_id": "device-123", "device_secret": client.device_secret}


def test_reuses_credentials_file_without_registering_again(isolated_cwd):
    CREDENTIALS_FILE.write_text(json.dumps({"device_id": "existing-device", "device_secret": "existing-secret"}))

    client = BrokerClient("https://broker.example.com")

    assert client.device_id == "existing-device"
    assert client.device_secret == "existing-secret"
    assert client.pairing_code is None


def test_request_sends_bearer_auth_header(isolated_cwd):
    CREDENTIALS_FILE.write_text(json.dumps({"device_id": "device-123", "device_secret": "shh"}))
    client = BrokerClient("https://broker.example.com")

    response = _response({"ok": True})
    request_mock = MagicMock(return_value=response)
    client.session.request = request_mock

    result = client._request("GET", "/some/path")

    assert result == {"ok": True}
    assert request_mock.call_args.kwargs["headers"]["Authorization"] == "Bearer shh"
    assert request_mock.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT


def test_get_config_parses_response(isolated_cwd):
    CREDENTIALS_FILE.write_text(json.dumps({"device_id": "device-123", "device_secret": "shh"}))
    client = BrokerClient("https://broker.example.com")
    client.session.request = MagicMock(return_value=_response({
        "interval": 20,
        "tfl": {"app_key": "tfl-key", "stop_ids": ["940GZZLUEUS"]},
        "weather": {"api_key": "weather-key", "location": "London"},
        "spotify": {"enabled": True},
        "glowmarkt": {"username": "me@example.com", "password": "hunter2"},
    }))

    config = client.get_config()

    assert config.interval == 20
    assert config.tfl.stop_ids == ["940GZZLUEUS"]
    assert config.spotify.enabled is True
    assert config.glowmarkt.username == "me@example.com"


def test_get_config_accepts_null_glowmarkt_credentials(isolated_cwd):
    """The common case: a device whose owner hasn't set up Glowmarkt on the
    broker. Sent as null, not omitted -- must parse, not raise."""
    CREDENTIALS_FILE.write_text(json.dumps({"device_id": "device-123", "device_secret": "shh"}))
    client = BrokerClient("https://broker.example.com")
    client.session.request = MagicMock(return_value=_response({
        "interval": 15,
        "tfl": {"app_key": "", "stop_ids": []},
        "weather": {"api_key": "", "location": ""},
        "spotify": {"enabled": False},
        "glowmarkt": {"username": None, "password": None},
    }))

    config = client.get_config()

    assert config.glowmarkt.username is None
    assert config.glowmarkt.password is None


def test_get_current_track_returns_none_when_broker_returns_null(isolated_cwd):
    CREDENTIALS_FILE.write_text(json.dumps({"device_id": "device-123", "device_secret": "shh"}))
    client = BrokerClient("https://broker.example.com")
    client.session.request = MagicMock(return_value=_response(None))

    assert client.get_current_track() is None


def test_get_current_track_passes_through_track_dict(isolated_cwd):
    CREDENTIALS_FILE.write_text(json.dumps({"device_id": "device-123", "device_secret": "shh"}))
    client = BrokerClient("https://broker.example.com")
    track = {"song": "A Song", "artist": "An Artist", "album": "An Album", "album_image": "http://x", "is_playing": True}
    client.session.request = MagicMock(return_value=_response(track))

    assert client.get_current_track() == track
