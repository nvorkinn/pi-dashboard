"""Visual regression tests for the composed display screen.

Each scenario builds panels directly from representative data -- no HTTP/TfL/
Glowmarkt mocking layer, that's covered by test_e2e_render_cycle.py -- and
compares the rendered PNG against a golden image checked into tests/images/.

Workflow (see the `snapshot` fixture in conftest.py):
    - `pytest tests/test_display_snapshots.py` compares against the committed
      goldens and fails with an actual-render + red-highlighted diff image
      (written to tests/images/_failures/) if anything changed.
    - `pytest tests/test_display_snapshots.py --update-snapshots` regenerates
      only the goldens that actually differ. Review the new PNGs (e.g. via a
      GitHub PR's image diff view) before committing them.

Two module-level things make this deterministic across runs/days:
    - `_CONTROLLER` is built once at import time (before any test's `isolated_cwd`
      fixture has chdir'd), matching how DisplayLoop's own default argument
      constructs it -- avoids a real filesystem dependency on cwd for the
      hardware-detection import inside DisplayController.__init__.
    - `_freeze_time` monkeypatches `datetime.now()` everywhere the render path
      calls it (the "Updated: ..." footer and EnergyPanel's date headers), since
      otherwise every golden image would go stale the instant the clock ticked.
"""
import datetime as dt
import io

import pytest
import responses
from PIL import Image

import display.display
import display.energy_panel

# countdown.models must be imported before any display.* module: display.abstract_arrival_panel
# imports countdown.models, and countdown/__init__.py transitively imports back into
# display.abstract_arrival_panel (via tfl_client.py) -- importing a display.* module first
# re-enters it mid-initialization and raises ImportError. Every other test file avoids this
# by happening to import something from countdown first.
from countdown.models import BusArrival, MetroStopPoint, SingleStopPoint, TubeArrival
from display.bus_arrival_panel import BusArrivalPanel
from display.combined_arrival_panel import CombinedArrivalPanel
from display.display import DisplayController
from display.energy_panel import EnergyPanel
from display.tube_arrival_panel import TubeArrivalPanel
from display.weather_panel import WeatherPanel

_CONTROLLER = DisplayController()

_FROZEN_NOW = dt.datetime(2026, 1, 15, 12, 0, 0)


class _FrozenDatetime(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return _FROZEN_NOW


@pytest.fixture(autouse=True)
def _freeze_time(monkeypatch):
    monkeypatch.setattr(display.display, "datetime", _FrozenDatetime)
    monkeypatch.setattr(display.energy_panel, "datetime", _FrozenDatetime)


@pytest.fixture(autouse=True)
def _suppress_image_show(monkeypatch):
    """DisplayController falls back to img.show() off real hardware -- without
    this every test run would pop up an image viewer window."""
    monkeypatch.setattr(Image.Image, "show", lambda self, *a, **kw: None)


BUS_STOP = SingleStopPoint(
    naptanId="490000123W", commonName="Elephant & Castle", modes=["bus"],
    additionalProperties=[], stopType="NaptanPublicBusCoachTram", stopLetter="W",
)
TUBE_STOP = MetroStopPoint(
    naptanId="940GZZLUKNG", commonName="Kennington Underground Station",
    modes=["tube"], additionalProperties=[], stopType="NaptanMetroStation",
)

BUS_ARRIVALS = [
    BusArrival(naptanId="490000123W", lineName="N155", timeToStation=300, modeName="bus", destinationName="Somewhere"),
    BusArrival(naptanId="490000123W", lineName="P5", timeToStation=780, modeName="bus", destinationName="Peckham"),
]
TUBE_ARRIVALS = [
    TubeArrival(naptanId="940GZZLUKNG", lineName="Northern", timeToStation=120, modeName="tube",
                towards="Bank", destinationNaptanId=None),
    TubeArrival(naptanId="940GZZLUKNG", lineName="Northern", timeToStation=480, modeName="tube",
                towards="Morden", destinationNaptanId=None),
]

ENERGY = EnergyPanel(
    readings_day=[1.5, 2.25] * 12,
    readings_month=[12.0 + i * 0.3 for i in range(30)],
    readings_year=[200.0 + i * 15 for i in range(12)],
)


class _FakeWeather:
    """Minimal stand-in for pyowm's Weather -- WeatherPanel only ever touches
    these two members, so there's nothing gained by building a real one."""

    def __init__(self, weather_code: int, temp_c: float):
        self.weather_code = weather_code
        self._temp_c = temp_c

    def temperature(self, unit: str) -> dict[str, float]:
        return {"temp": self._temp_c}


WEATHER = WeatherPanel(_FakeWeather(weather_code=804, temp_c=14.2))

SPOTIFY_TRACK_PLAYING = {
    "song": "Around The World", "artist": "Daft Punk", "album": "Homework",
    "album_image": "https://example.com/album.jpg", "is_playing": True,
}
SPOTIFY_TRACK_PAUSED = {**SPOTIFY_TRACK_PLAYING, "is_playing": False}


def _album_art_bytes() -> bytes:
    """64x64 to match what auth-broker actually picks (the *smallest* of the sizes
    Spotify returns, same logic that used to live in this repo's spotify_client.py
    before Spotify calls moved server-side) -- a larger thumbnail here would
    overflow the panel's fixed height budget below the energy panel."""
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (30, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _bus_and_tube_arrivals() -> CombinedArrivalPanel:
    return CombinedArrivalPanel([
        BusArrivalPanel(BUS_STOP, BUS_ARRIVALS),
        TubeArrivalPanel(TUBE_STOP, TUBE_ARRIVALS),
    ])


def _bus_only_arrivals() -> CombinedArrivalPanel:
    return CombinedArrivalPanel([BusArrivalPanel(BUS_STOP, BUS_ARRIVALS)])


def _no_arrivals() -> CombinedArrivalPanel:
    return CombinedArrivalPanel([])


def test_screen_with_no_stops_configured(snapshot):
    img = _CONTROLLER.display_screen(_no_arrivals(), ENERGY, None, WEATHER)
    snapshot.assert_matches("screen_no_stops", img)


def test_screen_with_single_bus_stop(snapshot):
    img = _CONTROLLER.display_screen(_bus_only_arrivals(), ENERGY, None, WEATHER)
    snapshot.assert_matches("screen_single_bus_stop", img)


def test_screen_with_mixed_bus_and_tube(snapshot):
    img = _CONTROLLER.display_screen(_bus_and_tube_arrivals(), ENERGY, None, WEATHER)
    snapshot.assert_matches("screen_mixed_bus_and_tube", img)


def test_screen_without_weather_data_yet(snapshot):
    """Covers the case where the very first weather fetch hasn't completed yet --
    display_screen must not crash when weather_panel is still None."""
    img = _CONTROLLER.display_screen(_bus_only_arrivals(), ENERGY, None, None)
    snapshot.assert_matches("screen_no_weather", img)


@responses.activate
def test_screen_with_spotify_playing(snapshot):
    responses.add(responses.GET, SPOTIFY_TRACK_PLAYING["album_image"], body=_album_art_bytes(), content_type="image/png")
    img = _CONTROLLER.display_screen(_bus_only_arrivals(), ENERGY, SPOTIFY_TRACK_PLAYING, WEATHER)
    snapshot.assert_matches("screen_spotify_playing", img)


@responses.activate
def test_screen_with_spotify_paused(snapshot):
    responses.add(responses.GET, SPOTIFY_TRACK_PAUSED["album_image"], body=_album_art_bytes(), content_type="image/png")
    img = _CONTROLLER.display_screen(_bus_only_arrivals(), ENERGY, SPOTIFY_TRACK_PAUSED, WEATHER)
    snapshot.assert_matches("screen_spotify_paused", img)


def test_partial_screen_with_no_cached_state_yet(snapshot):
    """A partial-refresh cycle before energy/weather have ever been fetched --
    display_partial must not crash when those are still None."""
    img = _CONTROLLER.display_partial(_bus_and_tube_arrivals(), None, None, None)
    snapshot.assert_matches("partial_screen_no_cached_state", img)
