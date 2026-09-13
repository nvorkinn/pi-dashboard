"""End-to-end tests for one full display refresh cycle.

Unlike the unit tests, these exercise the *real* client code (TflClient, GlowClient)
against mocked HTTP responses via `responses`, all the way through to a real rendered
PIL image -- catching integration bugs (mismatched fields between layers, panel sizing)
that per-component unit tests miss by construction.

Spotify and weather are mocked at the client-method level rather than their underlying
HTTP APIs: SpotifyClient wraps spotipy's own OAuth flow, and WeatherClient is being
replaced with an Open-Meteo-based client (see #24) -- neither is "our" integration logic
in the way TfL/Glowmarkt parsing is, so there's nothing gained by faking their transport
layer here, and it would only go stale the moment #24/#21 land.
"""
import io

import responses
from PIL import Image

from countdown.app import DisplayState, run_display_cycle
from countdown.config_manager import AppConfig
from countdown.glow_client import GlowClient
from countdown.spotify_client import SpotifyClient
from countdown.tfl_client import TflClient
from countdown.weather_client import WeatherClient
from display.display import DisplayController

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
BUS_ARRIVALS_JSON = [{
    "naptanId": "490000123W", "lineName": "N155", "timeToStation": 300,
    "modeName": "bus", "destinationName": "Somewhere",
}]
METRO_ARRIVALS_JSON = [{
    "naptanId": "940GZZLUKNG", "lineName": "Northern", "timeToStation": 120,
    "modeName": "tube", "towards": "Bank", "destinationNaptanId": None,
}]


class _StubWeatherPanel:
    """Stands in for a real WeatherPanel -- weather is mocked at the client-method
    level (see module docstring), so this never touches pyowm/Open-Meteo internals."""

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
    responses.add(responses.GET, "https://api.glowmarkt.com/api/v0-1/virtualentity", json=[
        {"resources": [{"name": "electricity consumption", "resourceId": "elec-id"}]}
    ])
    responses.add(responses.GET, "https://api.glowmarkt.com/api/v0-1/resource/elec-id/readings", json={
        "data": [[1700000000, 1.5], [1700003600, 2.25]]
    })


def _make_config() -> AppConfig:
    """SpotifyOAuth validates client_id/secret eagerly at construction time, so a
    real SpotifyClient can't even be built without them -- dummy values are fine
    since Spotify is mocked at the method level anyway (see module docstring)."""
    config = AppConfig()
    config.spotify.client_id = "dummy-client-id"
    config.spotify.client_secret = "dummy-client-secret"
    return config


def _build_clients(config: AppConfig) -> tuple[TflClient, GlowClient, SpotifyClient, WeatherClient, str]:
    tfl = TflClient(config.tfl)
    glow = GlowClient(config)
    spotify = SpotifyClient(config.spotify)
    weather = WeatherClient(config.weather)
    resource_id = glow.get_electricity_resource_id()
    return tfl, glow, spotify, weather, resource_id


@responses.activate
def test_full_render_cycle_without_spotify_track(isolated_cwd, monkeypatch):
    config = _make_config()
    config.tfl.stop_ids = ["490000123W", "940GZZLUKNG"]
    _mock_tfl_and_glowmarkt(
        {"490000123W": BUS_STOP_JSON, "940GZZLUKNG": METRO_STOP_JSON},
        {"490000123W": BUS_ARRIVALS_JSON, "940GZZLUKNG": METRO_ARRIVALS_JSON},
    )

    tfl, glow, spotify, weather, resource_id = _build_clients(config)
    monkeypatch.setattr(spotify, "get_current_track", lambda: None)
    monkeypatch.setattr(weather, "get_weather", lambda: _StubWeatherPanel())

    display = DisplayController()
    monkeypatch.setattr(Image.Image, "show", lambda self, *a, **kw: None)

    state = DisplayState()
    page_count = run_display_cycle(display, tfl, glow, resource_id, spotify, weather, state)

    assert page_count == 1
    assert state.energy_panel is not None
    assert state.energy["day"] == [1.5, 2.25]
    assert state.current_track is None
    assert len(tfl.stops) == 2


@responses.activate
def test_full_render_cycle_with_spotify_track(isolated_cwd, monkeypatch):
    config = _make_config()
    config.tfl.stop_ids = ["490000123W"]
    _mock_tfl_and_glowmarkt(
        {"490000123W": BUS_STOP_JSON},
        {"490000123W": BUS_ARRIVALS_JSON},
    )
    responses.add(responses.GET, "https://example.com/album.jpg", body=_png_bytes(), content_type="image/png")

    tfl, glow, spotify, weather, resource_id = _build_clients(config)
    monkeypatch.setattr(spotify, "get_current_track", lambda: {
        "song": "Test Song", "artist": "Test Artist", "album": "Test Album",
        "album_image": "https://example.com/album.jpg", "is_playing": True,
    })
    monkeypatch.setattr(weather, "get_weather", lambda: _StubWeatherPanel())

    display = DisplayController()
    monkeypatch.setattr(Image.Image, "show", lambda self, *a, **kw: None)

    state = DisplayState()
    run_display_cycle(display, tfl, glow, resource_id, spotify, weather, state)

    assert state.current_track["song"] == "Test Song"


@responses.activate
def test_partial_render_cycle_reuses_prior_state_without_refetching(isolated_cwd, monkeypatch):
    """4 stops -> page_count=2, so page=1 lands on the partial-refresh branch, which
    must reuse the previous cycle's energy/weather/track state rather than refetching."""
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

    tfl, glow, spotify, weather, resource_id = _build_clients(config)
    monkeypatch.setattr(spotify, "get_current_track", lambda: None)
    monkeypatch.setattr(weather, "get_weather", lambda: _StubWeatherPanel())

    display = DisplayController()
    monkeypatch.setattr(Image.Image, "show", lambda self, *a, **kw: None)

    state = DisplayState()
    page_count = run_display_cycle(display, tfl, glow, resource_id, spotify, weather, state)
    assert page_count == 2
    first_cycle_energy_panel = state.energy_panel

    def glowmarkt_call_count() -> int:
        return sum(1 for call in responses.calls if "glowmarkt.com" in call.request.url)

    state.page = 1
    glow_calls_before = glowmarkt_call_count()
    run_display_cycle(display, tfl, glow, resource_id, spotify, weather, state)

    # Partial refresh must not have hit Glowmarkt again -- only the arrival panels
    # (which do get refreshed every cycle) should have caused new requests.
    assert glowmarkt_call_count() == glow_calls_before
    assert state.energy_panel is first_cycle_energy_panel
