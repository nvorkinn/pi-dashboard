import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
import responses
from requests.adapters import HTTPAdapter

from countdown.abstract_client import ClientStatus
from countdown.config_manager import GlowmarktConfig
from countdown.glow_client import GlowClient, _get_utc_offset
from countdown.http import DEFAULT_TIMEOUT

BASE_URL = GlowClient.base_url


@pytest.fixture(autouse=True)
def glowmarkt_api():
    """GlowClient authenticates and looks up its resource id in initialise(), so
    tests that call it need these two endpoints -- and anything *else* should fail
    loudly instead of reaching the real API (which rate-limits fake credentials
    with a 429)."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.add(responses.POST, f"{BASE_URL}/auth", json={"token": "initial-token"})
        rsps.add(
            responses.GET,
            f"{BASE_URL}/virtualentity",
            json=[{"resources": [{"name": "electricity consumption", "resourceId": "elec-id"}]}],
        )
        yield rsps


def make_client() -> GlowClient:
    return GlowClient(GlowmarktConfig(username="me@example.com", password="hunter2"))


def make_initialised_client() -> GlowClient:
    client = make_client()
    asyncio.run(client.initialise())
    return client


def test_construction_makes_no_requests(glowmarkt_api):
    client = make_client()

    assert client.token is None
    assert client.resource_id is None
    assert len(glowmarkt_api.calls) == 0


def test_initialise_authenticates_and_resolves_the_electricity_resource():
    client = make_initialised_client()

    assert client.token == "initial-token"
    assert client.resource_id == "elec-id"
    assert not client.is_disabled()


@pytest.mark.parametrize(
    "config",
    [GlowmarktConfig(), GlowmarktConfig(username="me@example.com"), GlowmarktConfig(password="hunter2")],
)
def test_without_full_credentials_client_is_disabled_and_makes_no_requests(glowmarkt_api, config):
    client = GlowClient(config)

    assert client.status == ClientStatus.DISABLED
    asyncio.run(client.initialise())
    assert asyncio.run(client.update()) is None
    assert len(glowmarkt_api.calls) == 0


def test_get_utc_offset_for_utc():
    now = datetime(2026, 1, 1, tzinfo=UTC)
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


def test_request_authenticates_once_when_it_has_no_token(monkeypatch):
    client = make_client()
    client.token = None
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
    monkeypatch.setattr(
        client,
        "_request",
        MagicMock(
            return_value=[
                {
                    "resources": [
                        {"name": "gas consumption", "resourceId": "gas-id"},
                        {"name": "electricity consumption", "resourceId": "elec-id"},
                    ]
                }
            ]
        ),
    )

    assert client.get_electricity_resource_id() == "elec-id"


def test_get_electricity_resource_id_raises_when_missing(monkeypatch):
    client = make_client()
    monkeypatch.setattr(
        client,
        "_request",
        MagicMock(return_value=[{"resources": [{"name": "gas consumption", "resourceId": "gas-id"}]}]),
    )

    with pytest.raises(ValueError):
        client.get_electricity_resource_id()


def test_get_readings_parses_epoch_and_iso_timestamps(glowmarkt_api):
    glowmarkt_api.add(
        responses.GET,
        f"{BASE_URL}/resource/elec-id/readings",
        json={"data": [[1700000000, 1.5], ["2023-11-14T23:00:00", 2.25]]},
    )
    client = make_initialised_client()

    readings = client._get_readings(datetime(2023, 11, 14, tzinfo=UTC), datetime(2023, 11, 15, tzinfo=UTC), "PT1H")

    assert readings == [
        (datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC), 1.5),
        (datetime(2023, 11, 14, 23, 0, tzinfo=UTC), 2.25),
    ]
    request = glowmarkt_api.calls[-1].request
    assert "period=PT1H" in request.url
    assert request.headers["token"] == "initial-token"


def test_update_returns_a_panel_and_rotates_through_the_three_pages(monkeypatch):
    client = make_client()
    monkeypatch.setattr(client, "_get_readings", MagicMock(return_value=[]))

    pages = [asyncio.run(client.update()).page_index for _ in range(4)]

    assert pages == [0, 1, 2, 0]
