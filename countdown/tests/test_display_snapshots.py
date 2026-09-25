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

# `countdown` must be imported before any display.* module: countdown/__init__.py
# imports the whole app, which imports display.display, which imports back into
# countdown.* -- so importing a display.* module first re-enters it mid-initialisation
# and raises ImportError. Every other test file avoids this by happening to import
# something from countdown first.
import countdown  # noqa: F401, I001
import display.display
import display.energy_panel
from countdown.api_registry import ClientClasses
from countdown.glow_client import GlowClient
from countdown.models import (
    BusArrival,
    MetroStopPoint,
    Queue,
    SingleStopPoint,
    TubeArrival,
    Weather,
)
from countdown.notice_board_client import NoticeBoardClient
from countdown.notices.notice import Notice, Severity
from countdown.spotify_client import SpotifyClient
from countdown.tfl_client import TflClient
from countdown.weather_client import WeatherClient
from display.bus_arrival_panel import BusArrivalPanel
from display.combined_arrival_panel import CombinedArrivalPanel
from display.display import DisplayController
from display.empty_panel import EmptyPanel
from display.energy_panel import EnergyPanel
from display.notice_board_panel import NoticeBoardPanel
from display.pairing_code_panel import PairingCodePanel
from display.panel import Panel
from display.setup_panel import SetupPanel
from display.splash_panel import SplashPanel
from display.spotify_panel import SpotifyPanel
from display.tube_arrival_panel import TubeArrivalPanel
from display.weather_panel import WeatherPanel

_CONTROLLER = DisplayController()
EVERYTHING = frozenset(ClientClasses)
NO_GLOWMARKT = EVERYTHING - {ClientClasses.GLOWMARKT}


@pytest.fixture(autouse=True)
def _full_layout():
    """_CONTROLLER is shared, so each test starts from the full layout (a test that wants
    another sets it) rather than whichever one the previous test left behind."""
    _CONTROLLER.use_layout(EVERYTHING)


_FROZEN_NOW = dt.datetime(2026, 1, 15, 12, 0, 0)


class _FrozenDatetime(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return _FROZEN_NOW


@pytest.fixture(autouse=True)
def _freeze_time(monkeypatch):
    monkeypatch.setattr(display.energy_panel, "datetime", _FrozenDatetime)


@pytest.fixture(autouse=True)
def _suppress_image_show(monkeypatch):
    """DisplayController falls back to img.show() off real hardware -- without
    this every test run would pop up an image viewer window."""
    monkeypatch.setattr(Image.Image, "show", lambda self, *a, **kw: None)


BUS_STOP = SingleStopPoint(
    naptanId="490000123W",
    commonName="Elephant & Castle",
    modes=["bus"],
    additionalProperties=[],
    stopType="NaptanPublicBusCoachTram",
    stopLetter="W",
)
TUBE_STOP = MetroStopPoint(
    naptanId="940GZZLUKNG",
    commonName="Kennington Underground Station",
    modes=["tube"],
    additionalProperties=[],
    stopType="NaptanMetroStation",
)

BUS_ARRIVALS = [
    BusArrival(naptanId="490000123W", lineName="N155", timeToStation=300, modeName="bus", destinationName="Somewhere"),
    BusArrival(naptanId="490000123W", lineName="P5", timeToStation=780, modeName="bus", destinationName="Peckham"),
]
TUBE_ARRIVALS = [
    TubeArrival(
        naptanId="940GZZLUKNG",
        lineName="Northern",
        timeToStation=120,
        modeName="tube",
        towards="Bank",
        destinationNaptanId=None,
    ),
    TubeArrival(
        naptanId="940GZZLUKNG",
        lineName="Northern",
        timeToStation=480,
        modeName="tube",
        towards="Morden",
        destinationNaptanId=None,
    ),
]

ENERGY = EnergyPanel(
    [
        {"start": (_FROZEN_NOW - dt.timedelta(hours=23 - hour)).isoformat(), "kwh": 0.4 + (hour % 6) * 0.25}
        for hour in range(24)
    ],
    0,
)


WEATHER = WeatherPanel(
    Weather(temperature=14.2, weather_code=3, is_day=True, high=18.4, low=9.1, precipitation_probability=40)
)

ALBUM_ART_URL = "https://example.com/album.jpg"


def _track(name: str, artist: str, album: str) -> dict:
    return {
        "name": name,
        "artists": [{"name": artist}],
        "album": {"name": album, "images": [{"width": 64, "height": 64, "url": ALBUM_ART_URL}]},
        "duration_ms": 427_000,
    }


SPOTIFY_QUEUE = Queue.model_validate(
    {
        "currently_playing": _track("Around The World", "Daft Punk", "Homework"),
        "queue": [_track("Da Funk", "Daft Punk", "Homework")],
    }
)
SPOTIFY_QUEUE_LAST_TRACK = SPOTIFY_QUEUE.model_copy(update={"queue": []})


def _album_art_bytes() -> bytes:
    """The album's only image, and a small one: thumbnail() never scales up, so it
    stays 64x64 in the 120px-high panel."""
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (30, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _bus_and_tube_arrivals() -> CombinedArrivalPanel:
    return CombinedArrivalPanel(
        [
            BusArrivalPanel(BUS_STOP, BUS_ARRIVALS),
            TubeArrivalPanel(TUBE_STOP, TUBE_ARRIVALS),
        ]
    )


def _bus_only_arrivals() -> CombinedArrivalPanel:
    return CombinedArrivalPanel([BusArrivalPanel(BUS_STOP, BUS_ARRIVALS)])


def _four_stop_arrivals() -> CombinedArrivalPanel:
    """Two bus stops and two stations, for the layout with room for four."""
    other_bus_stop = BUS_STOP.model_copy(update={"common_name": "Walworth Road", "stop_letter": "E"})
    other_station = TUBE_STOP.model_copy(update={"common_name": "Oval Underground Station"})
    return CombinedArrivalPanel(
        [
            BusArrivalPanel(BUS_STOP, BUS_ARRIVALS),
            TubeArrivalPanel(TUBE_STOP, TUBE_ARRIVALS),
            BusArrivalPanel(other_bus_stop, BUS_ARRIVALS),
            TubeArrivalPanel(other_station, TUBE_ARRIVALS),
        ]
    )


SPOTIFY_NOT_CONFIGURED = SpotifyClient.message_panel("Not configured")

NOTICES = NoticeBoardPanel(
    [
        Notice("Met Office", Severity.SEVERE, "Red warning: wind until Fri 21:00"),
        Notice("Northern", Severity.WARNING, "Severe delays due to a signal failure at Camden Town."),
        Notice("Circle", Severity.INFO, "Issues Reported"),
        Notice("TfL", Severity.INFO, "Elephant & Castle: The lifts at the Northern line entrance are out of service"),
        Notice("Central", Severity.PLANNED, "Saturday 26 September, no service between Marble Arch and Loughton."),
    ]
)


def _panels(
    arrivals: Panel,
    energy: Panel = ENERGY,
    weather: Panel = WEATHER,
    spotify: Panel = SPOTIFY_NOT_CONFIGURED,
    notices: Panel = NOTICES,
) -> dict[str, Panel]:
    """What ApiRegistry.update_all() hands DisplayController.display_screen(): a panel
    for every API, a MessagePanel where one has nothing to show."""
    return {
        ClientClasses.TFL.api_name: arrivals,
        ClientClasses.GLOWMARKT.api_name: energy,
        ClientClasses.WEATHER.api_name: weather,
        ClientClasses.SPOTIFY.api_name: spotify,
        ClientClasses.NOTICE_BOARD.api_name: notices,
    }


def test_screen_with_no_stops_configured(snapshot):
    img = _CONTROLLER.display_screen(_panels(TflClient.message_panel("No stops set")))
    snapshot.assert_matches("screen_no_stops", img)


def test_screen_with_single_bus_stop(snapshot):
    img = _CONTROLLER.display_screen(_panels(_bus_only_arrivals()))
    snapshot.assert_matches("screen_single_bus_stop", img)


def test_screen_with_mixed_bus_and_tube(snapshot):
    img = _CONTROLLER.display_screen(_panels(_bus_and_tube_arrivals()))
    snapshot.assert_matches("screen_mixed_bus_and_tube", img)


def test_screen_without_weather_data_yet(snapshot):
    """The weather has never been fetched successfully: its area says so."""
    img = _CONTROLLER.display_screen(
        _panels(_bus_only_arrivals(), weather=WeatherClient.message_panel("Could not connect"))
    )
    snapshot.assert_matches("screen_no_weather", img)


def test_screen_without_energy_panel(snapshot):
    """Glowmarkt not set up (the common case for a gifted device): no energy column, and
    the notices and Spotify take the full width instead."""
    _CONTROLLER.use_layout(NO_GLOWMARKT)
    img = _CONTROLLER.display_screen(_panels(_bus_only_arrivals(), energy=GlowClient.message_panel("Not configured")))
    snapshot.assert_matches("screen_no_energy", img)


@responses.activate
def test_screen_without_energy_panel_playing_spotify(snapshot):
    """Spotify at the full width it gets without the energy column."""
    responses.add(responses.GET, ALBUM_ART_URL, body=_album_art_bytes(), content_type="image/png")
    _CONTROLLER.use_layout(NO_GLOWMARKT)
    img = _CONTROLLER.display_screen(
        _panels(
            _bus_only_arrivals(),
            energy=GlowClient.message_panel("Not configured"),
            spotify=SpotifyPanel(SPOTIFY_QUEUE),
        )
    )
    snapshot.assert_matches("screen_no_energy_spotify_playing", img)


def test_screen_with_no_notices(snapshot):
    img = _CONTROLLER.display_screen(
        _panels(_bus_only_arrivals(), notices=NoticeBoardClient.message_panel("All clear"))
    )
    snapshot.assert_matches("screen_no_notices", img)


def test_screen_without_spotify(snapshot):
    """GlowComposer: the notices under the arrivals, the energy chart under the weather."""
    _CONTROLLER.use_layout(EVERYTHING - {ClientClasses.SPOTIFY})
    img = _CONTROLLER.display_screen(_panels(_bus_and_tube_arrivals()))
    snapshot.assert_matches("screen_no_spotify", img)


def test_screen_with_four_stops_and_neither_spotify_nor_energy(snapshot):
    """BaseComposer: four stops in a 2x2 grid beside the weather, the notices below."""
    _CONTROLLER.use_layout(EVERYTHING - {ClientClasses.SPOTIFY, ClientClasses.GLOWMARKT})
    img = _CONTROLLER.display_screen(_panels(_four_stop_arrivals()))
    snapshot.assert_matches("screen_four_stops", img)


def test_splash_screen_when_the_broker_cannot_be_reached(snapshot):
    img = SplashPanel().render(display.display.TOTAL_WIDTH, display.display.TOTAL_HEIGHT)
    # A text-only screen with large glyphs: Ubuntu (CI) lays the same text out a pixel or so
    # differently from macOS, which put the mean difference at ~0.011 -- over the default
    # 0.005 -- with the same words in the same places. Measured from CI's failure artifact.
    snapshot.assert_matches("screen_splash", img, threshold=0.02)


def test_empty_screen_stays_clear_of_the_screen_edges():
    img = EmptyPanel().render(display.display.TOTAL_WIDTH, display.display.TOTAL_HEIGHT).convert("L")
    width, height = img.size

    for edge in [(0, 0, 40, height), (width - 40, 0, width, height)]:
        assert img.crop(edge).getextrema() == (255, 255)


def test_setup_checklist_screen(snapshot):
    img = SetupPanel(["a weather location", "a bus or tube stop"]).render(
        display.display.TOTAL_WIDTH, display.display.TOTAL_HEIGHT
    )
    snapshot.assert_matches("screen_setup_checklist", img, threshold=0.02)


@pytest.mark.parametrize("missing", [["a weather location"], ["a weather location", "a bus or tube stop"], ["x"] * 4])
def test_setup_checklist_stays_on_the_screen(missing):
    img = SetupPanel(missing).render(display.display.TOTAL_WIDTH, display.display.TOTAL_HEIGHT).convert("L")
    width, height = img.size

    for edge in [
        (0, 0, 20, height),
        (width - 20, 0, width, height),
        (0, 0, width, 10),
        (0, height - 10, width, height),
    ]:
        assert img.crop(edge).getextrema() == (255, 255)


def test_splash_text_stays_clear_of_the_screen_edges():
    """The text is big; a longer line or a bigger font must not run off the panel."""
    img = SplashPanel().render(display.display.TOTAL_WIDTH, display.display.TOTAL_HEIGHT).convert("L")
    width, height = img.size

    for edge in [(0, 0, 20, height), (width - 20, 0, width, height)]:
        assert img.crop(edge).getextrema() == (255, 255)  # nothing but white


def test_screen_with_no_panels_at_all_says_there_is_nothing_to_show(snapshot):
    """First cycle after boot, a paired device nobody's set up yet, or every API failing:
    a message saying so, not a blank white screen that looks broken (or a crash)."""
    img = _CONTROLLER.display_screen({})
    assert img.size == (display.display.TOTAL_WIDTH, display.display.TOTAL_HEIGHT)
    # Text-only and large: CI renders it ~1% differently from macOS (see screen_splash).
    snapshot.assert_matches("screen_nothing_to_show", img, threshold=0.02)


@responses.activate
def test_screen_with_spotify_playing(snapshot):
    responses.add(responses.GET, ALBUM_ART_URL, body=_album_art_bytes(), content_type="image/png")
    img = _CONTROLLER.display_screen(_panels(_bus_only_arrivals(), spotify=SpotifyPanel(SPOTIFY_QUEUE)))
    snapshot.assert_matches("screen_spotify_playing", img)


@responses.activate
def test_screen_with_spotify_playing_the_last_queued_track(snapshot):
    """Nothing up next: that line is left out rather than drawn empty."""
    responses.add(responses.GET, ALBUM_ART_URL, body=_album_art_bytes(), content_type="image/png")
    img = _CONTROLLER.display_screen(_panels(_bus_only_arrivals(), spotify=SpotifyPanel(SPOTIFY_QUEUE_LAST_TRACK)))
    snapshot.assert_matches("screen_spotify_last_track", img)


def test_weather_panel_rainy_night(snapshot):
    """A different code and the night variant, at the shorter height the panel gets
    while a Spotify track is playing."""
    panel = WeatherPanel(
        Weather(temperature=8.6, weather_code=63, is_day=False, high=11, low=6, precipitation_probability=85)
    )
    # The panel is small and mostly text, so the same handful of anti-aliased pixels
    # that differ between macOS and Linux weigh more here than in a full-screen
    # snapshot (CI measured 0.0059 against the default 0.005, all on the glyph edges).
    snapshot.assert_matches("weather_rainy_night", panel.render(528, 170), threshold=0.01)


def test_pairing_code_screen(snapshot):
    img = PairingCodePanel("C4FFEZ", "7218485b654f", has_changed=True).render(
        display.display.TOTAL_WIDTH, display.display.TOTAL_HEIGHT
    )
    snapshot.assert_matches("screen_pairing_code", img, threshold=0.02)


@pytest.mark.parametrize("code", ["C4FFEZ", "ABCDEFGH", "ABCDEFGHJKLM"])
def test_pairing_code_stays_on_the_screen_whatever_its_length(code):
    img = (
        PairingCodePanel(code, "7218485b654f", has_changed=True)
        .render(display.display.TOTAL_WIDTH, display.display.TOTAL_HEIGHT)
        .convert("L")
    )
    width, height = img.size

    for edge in [(0, 0, 30, height), (width - 30, 0, width, height)]:
        assert img.crop(edge).getextrema() == (255, 255)


def test_pairing_screen_without_a_code_draws_no_boxes():
    img = PairingCodePanel(None, "7218485b654f", has_changed=True).render(
        display.display.TOTAL_WIDTH, display.display.TOTAL_HEIGHT
    )

    assert img.convert("L").crop((0, 232, 800, 342)).getextrema() == (255, 255)
