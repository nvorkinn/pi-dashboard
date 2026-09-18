from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from requests.adapters import HTTPAdapter

from countdown.config_manager import GlowmarktConfig
from countdown.glow_client import GlowClient, _get_utc_offset
from countdown.http import DEFAULT_TIMEOUT


def make_client() -> GlowClient:
    return GlowClient(GlowmarktConfig(username="me@example.com", password="hunter2"))


def test_get_utc_offset_for_utc():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert _get_utc_offset(now) == "0"


def test_authenticate_stores_token(monkeypatch):
    client = make_client()
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {"token": "abc123"}
    monkeypatch.setattr(client.session, "post", MagicMock(return_value=fake_response))

    client._authenticate()

    assert client.token == "abc123"


def test_authenticate_passes_a_timeout(monkeypatch):
    client = make_client()
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock()
    fake_response.json.return_value = {"token": "abc123"}
    post_mock = MagicMock(return_value=fake_response)
    monkeypatch.setattr(client.session, "post", post_mock)

    client._authenticate()

    assert post_mock.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT


def test_request_authenticates_lazily_once(monkeypatch):
    client = make_client()
    auth_response = MagicMock()
    auth_response.raise_for_status = MagicMock()
    auth_response.json.return_value = {"token": "abc123"}
    post_mock = MagicMock(return_value=auth_response)
    monkeypatch.setattr(client.session, "post", post_mock)

    data_response = MagicMock()
    data_response.status_code = 200
    data_response.raise_for_status = MagicMock()
    data_response.json.return_value = {"ok": True}
    request_mock = MagicMock(return_value=data_response)
    monkeypatch.setattr(client.session, "request", request_mock)

    result = client._request("GET", "/some/endpoint")

    assert result == {"ok": True}
    post_mock.assert_called_once()
    assert request_mock.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT


def test_request_reauthenticates_on_401(monkeypatch):
    client = make_client()
    client.token = "stale-token"

    auth_response = MagicMock()
    auth_response.raise_for_status = MagicMock()
    auth_response.json.return_value = {"token": "fresh-token"}
    monkeypatch.setattr(client.session, "post", MagicMock(return_value=auth_response))

    unauthorized_response = MagicMock()
    unauthorized_response.status_code = 401
    unauthorized_response.raise_for_status = MagicMock()

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.raise_for_status = MagicMock()
    ok_response.json.return_value = {"ok": True}

    request_mock = MagicMock(side_effect=[unauthorized_response, ok_response])
    monkeypatch.setattr(client.session, "request", request_mock)

    result = client._request("GET", "/some/endpoint")

    assert result == {"ok": True}
    assert client.token == "fresh-token"
    assert request_mock.call_count == 2


def test_session_has_retry_adapter_mounted():
    client = make_client()
    adapter = client.session.get_adapter("https://api.glowmarkt.com")
    assert isinstance(adapter, HTTPAdapter)
    assert adapter.max_retries.total == 3


def test_get_electricity_resource_id_finds_electricity_entry(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, "_request", MagicMock(return_value=[
        {"resources": [
            {"name": "gas consumption", "resourceId": "gas-id"},
            {"name": "electricity consumption", "resourceId": "elec-id"},
        ]}
    ]))

    assert client.get_electricity_resource_id() == "elec-id"


def test_get_electricity_resource_id_raises_when_missing(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, "_request", MagicMock(return_value=[
        {"resources": [{"name": "gas consumption", "resourceId": "gas-id"}]}
    ]))

    with pytest.raises(ValueError):
        client.get_electricity_resource_id()


def test_get_day_readings_extracts_values(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, "_request", MagicMock(return_value={
        "data": [[1700000000, 1.5], [1700003600, 2.25]]
    }))

    assert client.get_day_readings("resource-id") == [1.5, 2.25]
