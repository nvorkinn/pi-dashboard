import asyncio
import json
from datetime import timedelta

import pytest
import responses
from pydantic import ValidationError

from countdown.config_manager import SpotifyConfig
from countdown.spotify_client import CREDENTIALS_FILE, SpotifyClient
from display.spotify_panel import SpotifyPanel

BROKER_URL = "https://broker.example.com"
QUEUE_URL = f"{BROKER_URL}/api/devices/device-123/queue"


def track(name: str) -> dict:
    return {
        "name": name,
        "artists": [{"name": "An Artist"}, {"name": "Another Artist"}],
        "album": {"name": "An Album", "images": [{"width": 640, "height": 640, "url": "https://example.com/a.jpg"}]},
        "duration_ms": 180_000,
    }


QUEUE = {"currently_playing": track("A Song"), "queue": [track("Next Song")]}


@pytest.fixture
def client(isolated_cwd, monkeypatch) -> SpotifyClient:
    """A SpotifyClient for a device that's already registered with the broker (the
    BrokerClient owns registration; this one only reads the credentials it saved)."""
    monkeypatch.setenv("BROKER_URL", BROKER_URL)
    CREDENTIALS_FILE.write_text(json.dumps({"device_id": "device-123", "device_secret": "shh"}))
    return SpotifyClient(SpotifyConfig(enabled=True))


@responses.activate
def test_update_wraps_the_queue_in_a_panel(client):
    responses.add(responses.GET, QUEUE_URL, json=QUEUE)

    panel = asyncio.run(client.update())

    assert isinstance(panel, SpotifyPanel)
    assert panel.queue.currently_playing.name == "A Song"
    assert panel.queue.currently_playing.duration_ms == timedelta(minutes=3)
    assert [t.name for t in panel.queue.queue] == ["Next Song"]


@responses.activate
def test_update_sends_the_device_secret_as_a_bearer_token(client):
    responses.add(responses.GET, QUEUE_URL, json=QUEUE)

    asyncio.run(client.update())

    request = responses.calls[0].request
    assert request.headers["Authorization"] == "Bearer shh"


@responses.activate
def test_update_says_so_when_nothing_is_playing(client):
    """Even with tracks still queued up: the panel is about what's playing."""
    responses.add(responses.GET, QUEUE_URL, json={"currently_playing": None, "queue": [track("Next Song")]})

    assert asyncio.run(client.update()).message == "Nothing playing on:"


@responses.activate
def test_update_raises_on_a_malformed_queue(client):
    responses.add(responses.GET, QUEUE_URL, json={"currently_playing": {"name": "missing everything else"}})

    with pytest.raises(ValidationError):
        asyncio.run(client.update())
