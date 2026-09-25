import asyncio
import json

import pytest
import responses
from pydantic import ValidationError

from countdown.config_manager import SpotifyConfig
from countdown.spotify_client import CREDENTIALS_FILE, SpotifyClient
from display.spotify_panel import SpotifyPanel

BROKER_URL = "https://broker.example.com"
NOW_PLAYING_URL = f"{BROKER_URL}/api/devices/device-123/now-playing"
TRACK = {
    "song": "A Song",
    "artist": "An Artist",
    "album": "An Album",
    "album_image": "https://example.com/album.jpg",
    "is_playing": True,
}


@pytest.fixture
def client(isolated_cwd, monkeypatch) -> SpotifyClient:
    """A SpotifyClient for a device that's already registered with the broker (the
    BrokerClient owns registration; this one only reads the credentials it saved)."""
    monkeypatch.setenv("BROKER_URL", BROKER_URL)
    CREDENTIALS_FILE.write_text(json.dumps({"device_id": "device-123", "device_secret": "shh"}))
    return SpotifyClient(SpotifyConfig(enabled=True))


@responses.activate
def test_update_wraps_the_now_playing_track_in_a_panel(client):
    responses.add(responses.GET, NOW_PLAYING_URL, json=TRACK)

    panel = asyncio.run(client.update())

    assert isinstance(panel, SpotifyPanel)
    assert panel.playingRightNow.song == "A Song"
    assert panel.playingRightNow.is_playing is True


@responses.activate
def test_update_sends_the_device_secret_as_a_bearer_token(client):
    responses.add(responses.GET, NOW_PLAYING_URL, json=TRACK)

    asyncio.run(client.update())

    request = responses.calls[0].request
    assert request.headers["Authorization"] == "Bearer shh"


@responses.activate
def test_update_says_so_when_nothing_is_playing(client):
    """The broker answers null (not an empty object) when there's no current track --
    that means "nothing playing", not a validation failure."""
    responses.add(responses.GET, NOW_PLAYING_URL, body="null", content_type="application/json")

    assert asyncio.run(client.update()).message == "Nothing playing on:"


@responses.activate
def test_update_raises_on_a_malformed_track(client):
    responses.add(responses.GET, NOW_PLAYING_URL, json={"song": "missing everything else"})

    with pytest.raises(ValidationError):
        asyncio.run(client.update())
