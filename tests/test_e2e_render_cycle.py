"""End-to-end tests for one full display refresh cycle.

Unlike the unit tests, these exercise the *real* client code (TflClient, GlowClient)
against mocked HTTP responses via `responses`, all the way through to a real rendered
PIL image -- catching integration bugs (mismatched fields between layers, panel sizing)
that per-component unit tests miss by construction.

Spotify and weather are mocked at the client-method level rather than their underlying
HTTP APIs: WeatherClient has its own test suite (test_weather_client.py), and
BrokerClient.get_current_track() is a thin passthrough to auth-broker (which has its
own test suite) -- neither is "our" integration logic in the way TfL/Glowmarkt parsing
is, so there's nothing gained by faking their transport layer here.

Most of these tests build a DisplayLoop directly from a `config`/`pairing_code`
override, which leaves BrokerClient.get_config() unmocked -- with no matching
`responses` registration, `responses` raises ConnectionError on that call, which
safe_fetch swallows, exercising the "broker unreachable" resilience path for free
and keeping those tests focused on TfL/Glowmarkt/Spotify. fetch_app_config() itself
-- both the real-broker-response path and that same unreachable fallback -- gets
its own dedicated coverage further down instead.
"""

import io
import json
from pathlib import Path

import responses
from PIL import Image

from countdown.broker_client import BrokerClient
from countdown.config_manager import AppConfig
from countdown.display_loop import DisplayLoop, fetch_app_config

TEST_BROKER_URL = "https://broker.example.com"


def _app_config_json(pairing_code: str | None = None, interval: int = 0) -> dict:
    return {
        "interval": interval,
        "tfl": {"app_key": "", "stop_ids": []},
        "weather": {"api_key": "", "location": ""},
        "spotify": {"enabled": False},
        "glowmarkt": {"username": None, "password": None},
        "pairing_code": pairing_code,
    }


BUS_STOP_JSON = {
    "naptanId": "490000123W",
    "commonName": "Elephant & Castle",
    "modes": ["bus"],
    "additionalProperties": [],
    "children": [],
    "stopType": "NaptanPublicBusCoachTram",
    "stopLetter": "W",
}
METRO_STOP_JSON = {
    "naptanId": "940GZZLUKNG",
    "commonName": "Kennington Underground Station",
    "modes": ["tube"],
    "additionalProperties": [],
    "children": [],
    "stopType": "NaptanMetroStation",
}
BUS_ARRIVALS_JSON = [
    {
        "naptanId": "490000123W",
        "lineName": "N155",
        "timeToStation": 300,
        "modeName": "bus",
        "destinationName": "Somewhere",
    }
]
METRO_ARRIVALS_JSON = [
    {
        "naptanId": "940GZZLUKNG",
        "lineName": "Northern",
        "timeToStation": 120,
        "modeName": "tube",
        "towards": "Bank",
        "destinationNaptanId": None,
    }
]


class _StubWeatherPanel:
    """Stands in for a real WeatherPanel -- weather is mocked at the client-method
    level (see module docstring), so this never touches Open-Meteo internals."""

    def render(self, image_width: int, image_height: int) -> Image.Image:
        return Image.new("RGBA", (max(image_width, 1), max(image_height, 1)), (255, 255, 255, 0))


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "blue").save(buf, format="PNG")
    return buf.getvalue()


def _mock_tfl_and_glowmarkt(stop_json_by_id: dict, arrivals_json_by_id: dict) -> None:
    for stop_id, stop_json in stop_json_by_id.items():
        responses.add(responses.GET, f"https://api.tfl.gov.uk/StopPoint/{stop_id}", json=stop_json)
    for stop_id, arrivals_json in arrivals_json_by_id.items():
        responses.add(responses.GET, f"https://api.tfl.gov.uk/StopPoint/{stop_id}/Arrivals", json=arrivals_json)

    responses.add(responses.POST, "https://api.glowmarkt.com/api/v0-1/auth", json={"token": "fake-token"})
    responses.add(
        responses.GET,
        "https://api.glowmarkt.com/api/v0-1/virtualentity",
        json=[{"resources": [{"name": "electricity consumption", "resourceId": "elec-id"}]}],
    )
    responses.add(
        responses.GET,
        "https://api.glowmarkt.com/api/v0-1/resource/elec-id/readings",
        json={"data": [[1700000000, 1.5], [1700003600, 2.25]]},
    )


def _make_config() -> AppConfig:
    config = AppConfig()
    config.interval = 0  # Means we just run the loop
    # Real (dummy) credentials, since these tests mock Glowmarkt's endpoints and
    # exercise that path -- DisplayLoop now skips Glowmarkt entirely when
    # username/password are empty (the common case for most real devices).
    config.glowmarkt.username = "dummy@example.com"
    config.glowmarkt.password = "dummy-password"
    return config


def _seed_credentials() -> None:
    # BrokerClient registers itself on construction if no credentials file exists --
    # seed one so tests load it instead of making a real (unmocked) network call.
    Path(".auth_broker_device").write_text(json.dumps({"device_id": "test-device", "device_secret": "test-secret"}))


def _build_loop(
    config: AppConfig,
    monkeypatch,
    spotify_track: dict | None,
    pairing_code: str | None = None,
    show_callback=lambda self, *a, **kw: None,
) -> DisplayLoop:
    _seed_credentials()
    broker = BrokerClient(TEST_BROKER_URL)
    # Seeds broker's own cache too (get_pairing_code_panel, not a bare
    # PairingCodePanel(...)), same as fetch_app_config() does for real -- so a
    # test that later re-polls with the same code sees has_changed=False, not a
    # spurious "first time" every call.
    pairing_code_panel = broker.get_pairing_code_panel(AppConfig.model_validate(_app_config_json(pairing_code)))
    loop = DisplayLoop(broker, config, pairing_code_panel)
    monkeypatch.setattr(loop.broker, "get_current_track", lambda: spotify_track)
    monkeypatch.setattr(loop.weather, "get_weather", lambda: _StubWeatherPanel())
    monkeypatch.setattr(Image.Image, "show", show_callback)
    return loop


@responses.activate
def test_full_render_cycle_without_spotify_track(isolated_cwd, monkeypatch):
    config = _make_config()
    config.tfl.stop_ids = ["490000123W", "940GZZLUKNG"]
    _mock_tfl_and_glowmarkt(
        {"490000123W": BUS_STOP_JSON, "940GZZLUKNG": METRO_STOP_JSON},
        {"490000123W": BUS_ARRIVALS_JSON, "940GZZLUKNG": METRO_ARRIVALS_JSON},
    )

    loop = _build_loop(config, monkeypatch, spotify_track=None)
    loop.run()

    assert loop.page_count == 1
    assert loop.energy["day"] == [1.5, 2.25]
    assert loop.current_track is None


@responses.activate
def test_full_render_cycle_skips_glowmarkt_when_credentials_empty(isolated_cwd, monkeypatch):
    """The common case: a gifted device whose owner never set up Glowmarkt on the
    broker. Deliberately doesn't mock any glowmarkt.com endpoint -- if DisplayLoop
    ever attempted a call, `responses` would raise ConnectionError for it, which
    would surface as a different, unrelated-looking failure below."""
    config = AppConfig()
    config.interval = 0
    config.tfl.stop_ids = ["490000123W"]
    assert config.glowmarkt.username is None and config.glowmarkt.password is None

    for stop_id, stop_json in {"490000123W": BUS_STOP_JSON}.items():
        responses.add(responses.GET, f"https://api.tfl.gov.uk/StopPoint/{stop_id}", json=stop_json)
    for stop_id, arrivals_json in {"490000123W": BUS_ARRIVALS_JSON}.items():
        responses.add(responses.GET, f"https://api.tfl.gov.uk/StopPoint/{stop_id}/Arrivals", json=arrivals_json)

    loop = _build_loop(config, monkeypatch, spotify_track=None)
    loop.run()

    assert loop.resource_id is None
    assert loop.energy == {"day": None, "month": None, "year": None}
    assert len(loop.tfl.stops) == 1


@responses.activate
def test_full_render_cycle_with_spotify_track(isolated_cwd, monkeypatch):
    config = _make_config()
    config.tfl.stop_ids = ["490000123W"]
    _mock_tfl_and_glowmarkt(
        {"490000123W": BUS_STOP_JSON},
        {"490000123W": BUS_ARRIVALS_JSON},
    )
    responses.add(responses.GET, "https://example.com/album.jpg", body=_png_bytes(), content_type="image/png")

    loop = _build_loop(
        config,
        monkeypatch,
        spotify_track={
            "song": "Test Song",
            "artist": "Test Artist",
            "album": "Test Album",
            "album_image": "https://example.com/album.jpg",
            "is_playing": True,
        },
    )
    loop.run()

    assert loop.current_track["song"] == "Test Song"


@responses.activate
def test_partial_render_cycle_reuses_prior_state_without_refetching(isolated_cwd, monkeypatch):
    """4 stops -> page_count=2, so page=1 lands on the partial-refresh branch, which
    must reuse the previous cycle's energy/weather/track state rather than refetching.
    (What a partial-refresh cycle actually looks like is covered separately as a
    golden-image scenario in test_display_snapshots.py -- this test is purely about
    the caching/refetch behaviour, not the rendered pixels.)"""
    config = _make_config()
    config.tfl.stop_ids = ["490000123W", "940GZZLUKNG", "490000456X", "940GZZLUABC"]
    _mock_tfl_and_glowmarkt(
        {
            "490000123W": BUS_STOP_JSON,
            "940GZZLUKNG": METRO_STOP_JSON,
            "490000456X": dict(BUS_STOP_JSON, naptanId="490000456X"),
            "940GZZLUABC": dict(METRO_STOP_JSON, naptanId="940GZZLUABC"),
        },
        {
            "490000123W": BUS_ARRIVALS_JSON,
            "940GZZLUKNG": METRO_ARRIVALS_JSON,
            "490000456X": BUS_ARRIVALS_JSON,
            "940GZZLUABC": METRO_ARRIVALS_JSON,
        },
    )

    loop = _build_loop(config, monkeypatch, spotify_track=None)
    loop.run()
    assert loop.page_count == 2
    energy_after_first_cycle = dict(loop.energy)

    def glowmarkt_call_count() -> int:
        return sum(1 for call in responses.calls if "glowmarkt.com" in call.request.url)

    loop.page = 1
    glow_calls_before = glowmarkt_call_count()
    loop.run()

    # Partial refresh must not have hit Glowmarkt again -- only the arrival panels
    # (which do get refreshed every cycle) should have caused new requests.
    assert glowmarkt_call_count() == glow_calls_before
    assert loop.energy == energy_after_first_cycle


@responses.activate
def test_run_shows_pairing_screen_and_skips_normal_display_while_unpaired(isolated_cwd, monkeypatch):
    """While a pairing code is active, run() shouldn't touch TfL/Glowmarkt/weather/
    Spotify at all -- none of those endpoints are mocked here, so a call to any of
    them would surface as an unrelated-looking ConnectionError failure below."""
    config = _make_config()
    config.tfl.stop_ids = ["490000123W"]

    loop = _build_loop(config, monkeypatch, spotify_track=None, pairing_code="ABC123")
    screens_shown = []
    monkeypatch.setattr(
        loop.display,
        "display_pairing_screen",
        lambda panel: screens_shown.append((panel.pairing_code, panel.device_id)),
    )

    loop.run()

    assert screens_shown == [("ABC123", "test-device")]
    assert loop.energy == {"day": None, "month": None, "year": None}


@responses.activate
def test_run_only_repaints_pairing_screen_when_code_changes(isolated_cwd, monkeypatch):
    """A full e-paper refresh is slow and visibly flashy -- repainting an unchanged
    pairing code every cycle for however long a device sits unpaired would be
    needless wear, not just noise. Unlike the test above, /config IS mocked here
    (always returning the same code) so refresh_broker_config() actually re-derives
    pairing_code_panel each cycle via BrokerClient's cache, instead of leaving the
    cycle-1 panel (and its has_changed=True) untouched forever."""
    config = _make_config()
    responses.add(
        responses.GET,
        f"{TEST_BROKER_URL}/api/devices/test-device/config",
        json=_app_config_json(pairing_code="ABC123", interval=0),
    )

    loop = _build_loop(config, monkeypatch, spotify_track=None, pairing_code="ABC123")
    screens_shown = []
    monkeypatch.setattr(loop.display, "display_pairing_screen", lambda panel: screens_shown.append(panel.pairing_code))

    loop.run()  # cycle 1: pairing_code_panel seeded by _build_loop, has_changed=True -> repaint
    loop.page = 0  # run() only executes once per call when interval == 0; call again to simulate cycle 2
    loop.run()  # cycle 2: refresh_broker_config() re-fetches the same code -> has_changed=False -> no repaint

    assert screens_shown == ["ABC123"]


@responses.activate
def test_fetch_app_config_uses_real_broker_response(isolated_cwd):
    _seed_credentials()
    broker = BrokerClient(TEST_BROKER_URL)
    responses.add(
        responses.GET,
        f"{TEST_BROKER_URL}/api/devices/test-device/config",
        json={
            "interval": 20,
            "tfl": {"app_key": "tfl-key", "stop_ids": ["940GZZLUEUS"]},
            "weather": {"api_key": "weather-key", "location": "London"},
            "spotify": {"enabled": True},
            "glowmarkt": {"username": None, "password": None},
            "pairing_code": "XYZ789",
        },
    )

    config, pairing_code_panel = fetch_app_config(broker)

    assert config.interval == 20
    assert config.tfl.stop_ids == ["940GZZLUEUS"]
    assert config.spotify.enabled is True
    assert pairing_code_panel.pairing_code == "XYZ789"
    assert pairing_code_panel.device_id == "test-device"
    assert pairing_code_panel.has_changed is True  # first time this device's ever checked


@responses.activate
def test_fetch_app_config_falls_back_to_empty_when_broker_unreachable(isolated_cwd):
    _seed_credentials()
    broker = BrokerClient(TEST_BROKER_URL)
    # /config deliberately left unmocked -- responses raises ConnectionError for it.

    config, pairing_code_panel = fetch_app_config(broker)

    assert config.tfl.stop_ids == []
    assert config.interval == 15
    assert pairing_code_panel.pairing_code is None
