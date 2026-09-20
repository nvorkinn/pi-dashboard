"""End-to-end tests for the display refresh cycle.

Unlike the unit tests, these exercise the *real* clients (TflClient, GlowClient,
WeatherClient, SpotifyClient), built by the real ApiRegistry inside DisplayLoop.run(),
against mocked HTTP responses via `responses`, all the way through to a real rendered
PIL image -- catching integration bugs (mismatched fields between layers, panel sizing,
a client's panel not reaching the screen) that per-component unit tests miss by
construction.

The clients are created inside run(), so there's nothing to monkeypatch on a
DisplayLoop beforehand: everything is faked at the transport layer instead. Two
things let a test drive a known number of cycles without waiting on a real clock:
`interval` is 1 (AppConfig rejects 0) and `asyncio.sleep` is replaced by a fake that
raises after N calls -- see _run_cycles().

Most tests build a DisplayLoop directly from a `config`/`pairing_code` override, which
leaves BrokerClient.get_config() unmocked -- with no matching `responses` registration,
`responses` raises ConnectionError on that call, which safe_fetch swallows, exercising
the "broker unreachable" resilience path for free and keeping those tests focused on
the APIs they're about. BrokerClient.fetch_app_config() has its own coverage in
test_broker_client.py.
"""

import asyncio
import datetime
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import responses
from config_factory import make_config
from PIL import Image

from countdown import display_loop
from countdown.broker_client import BrokerClient
from countdown.config_manager import AppConfig
from countdown.display_loop import DisplayLoop
from display.combined_arrival_panel import CombinedArrivalPanel
from display.energy_panel import EnergyPanel
from display.spotify_panel import SpotifyPanel
from display.weather_panel import WeatherPanel

TEST_BROKER_URL = "https://broker.example.com"
GLOWMARKT_URL = "https://api.glowmarkt.com/api/v0-1"
NOW_PLAYING_URL = f"{TEST_BROKER_URL}/api/devices/test-device/now-playing"


def _app_config_json(
    pairing_code: str | None = None, interval: int = 1, setup_missing: list[str] | None = None
) -> dict:
    return {
        "interval": interval,
        "tfl": {"app_key": "", "stop_ids": []},
        "weather": {"api_key": "", "location": ""},
        "spotify": {"enabled": False},
        "glowmarkt": {"username": None, "password": None},
        "pairing_code": pairing_code,
        "setup_missing": setup_missing or [],
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
TRACK_JSON = {
    "song": "Test Song",
    "artist": "Test Artist",
    "album": "Test Album",
    "album_image": "https://example.com/album.jpg",
    "is_playing": True,
}


class _StopLoop(Exception):
    """Raised by the fake sleep to break out of DisplayLoop.run()'s `while True`."""


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "blue").save(buf, format="PNG")
    return buf.getvalue()


def _mock_tfl(stop_json_by_id: dict, arrivals_json_by_id: dict) -> None:
    for stop_id, stop_json in stop_json_by_id.items():
        responses.add(responses.GET, f"https://api.tfl.gov.uk/StopPoint/{stop_id}", json=stop_json)
    for stop_id, arrivals_json in arrivals_json_by_id.items():
        responses.add(responses.GET, f"https://api.tfl.gov.uk/StopPoint/{stop_id}/Arrivals", json=arrivals_json)


def _mock_glowmarkt() -> None:
    responses.add(responses.POST, f"{GLOWMARKT_URL}/auth", json={"token": "fake-token"})
    responses.add(
        responses.GET,
        f"{GLOWMARKT_URL}/virtualentity",
        json=[{"resources": [{"name": "electricity consumption", "resourceId": "elec-id"}]}],
    )

    now = datetime.datetime.now().astimezone()
    four_hours_earlier = now - datetime.timedelta(hours=4)
    six_hours_earlier = now - datetime.timedelta(hours=6)
    responses.add(
        responses.GET,
        f"{GLOWMARKT_URL}/resource/elec-id/readings",
        json={"data": [[four_hours_earlier.timestamp(), 1.5], [six_hours_earlier.timestamp(), 2.25]]},
    )


def _mock_tfl_and_glowmarkt(stop_json_by_id: dict, arrivals_json_by_id: dict) -> None:
    _mock_tfl(stop_json_by_id, arrivals_json_by_id)
    _mock_glowmarkt()


def _make_config() -> AppConfig:
    config = make_config()
    config.interval = 1  # the fake sleep in _run_cycles() means this never actually waits
    # Real (dummy) credentials, since these tests mock Glowmarkt's endpoints and
    # exercise that path -- GlowClient stays disabled when they're empty (the common
    # case for most real devices).
    config.glowmarkt.username = "dummy@example.com"
    config.glowmarkt.password = "dummy-password"
    return config


def _seed_credentials() -> None:
    # BrokerClient registers itself in initialise() if no credentials file exists --
    # seed one so tests load it instead of making a real (unmocked) network call.
    Path(".auth_broker_device").write_text(json.dumps({"device_id": "test-device", "device_secret": "test-secret"}))


def _build_loop(config: AppConfig, monkeypatch, pairing_code: str | None = None) -> DisplayLoop:
    _seed_credentials()
    monkeypatch.setenv("BROKER_URL", TEST_BROKER_URL)  # SpotifyClient reads this
    broker = BrokerClient(TEST_BROKER_URL)
    asyncio.run(broker.initialise())
    # Seeds broker's own cache too (get_pairing_code_panel, not a bare
    # PairingCodePanel(...)), same as fetch_app_config() does for real -- so a
    # test that later re-polls with the same code sees has_changed=False, not a
    # spurious "first time" every call.
    pairing_code_panel = broker.get_pairing_code_panel(AppConfig.model_validate(_app_config_json(pairing_code)))
    monkeypatch.setattr(Image.Image, "show", lambda self, *a, **kw: None)
    return DisplayLoop(broker, config, pairing_code_panel)


def _spy_on_display_screen(loop: DisplayLoop, monkeypatch) -> list[dict]:
    """Records the panels dict of every display_screen() call (which still runs for
    real, so the whole render path is exercised too)."""
    seen: list[dict] = []
    original = loop.display.display_screen

    def spy(panels):
        seen.append(dict(panels))
        return original(panels)

    monkeypatch.setattr(loop.display, "display_screen", spy)
    return seen


def _run_cycles(loop: DisplayLoop, monkeypatch, cycles: int = 1) -> None:
    """Runs exactly `cycles` refresh cycles: the loop sleeps once after each, and the
    fake sleep stops it there (before the broker config refresh, on the last one)."""
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= cycles:
            raise _StopLoop

    monkeypatch.setattr(display_loop, "asyncio", SimpleNamespace(sleep=fake_sleep))
    with pytest.raises(_StopLoop):
        asyncio.run(loop.run())


def _calls_to(url_prefix: str) -> int:
    return sum(1 for call in responses.calls if call.request.url.startswith(url_prefix))


@responses.activate
def test_full_render_cycle_without_spotify_track(isolated_cwd, monkeypatch):
    config = _make_config()
    config.tfl.stop_ids = ["490000123W", "940GZZLUKNG"]
    _mock_tfl_and_glowmarkt(
        {"490000123W": BUS_STOP_JSON, "940GZZLUKNG": METRO_STOP_JSON},
        {"490000123W": BUS_ARRIVALS_JSON, "940GZZLUKNG": METRO_ARRIVALS_JSON},
    )
    loop = _build_loop(config, monkeypatch)
    shown = _spy_on_display_screen(loop, monkeypatch)

    _run_cycles(loop, monkeypatch)

    assert len(shown) == 1
    panels = shown[0]
    assert isinstance(panels["tfl"], CombinedArrivalPanel)
    assert len(panels["tfl"].arrival_panels) == 2
    assert isinstance(panels["glowmarkt"], EnergyPanel)
    assert panels["glowmarkt"].page_index == 0
    assert [reading["kwh"] for reading in panels["glowmarkt"].readings] == [2.25, 1.5]  # oldest first
    assert "spotify" not in panels  # not enabled, so never even built
    assert panels["weather"] is None  # no location configured


@responses.activate
def test_full_render_cycle_skips_glowmarkt_when_credentials_empty(isolated_cwd, monkeypatch):
    """The common case: a gifted device whose owner never set up Glowmarkt on the
    broker. Deliberately doesn't mock any glowmarkt.com endpoint -- if the client
    ever attempted a call, `responses` would raise ConnectionError for it, and the
    call count below would catch it."""
    config = make_config()
    config.interval = 1
    config.tfl.stop_ids = ["490000123W"]
    assert config.glowmarkt.username is None and config.glowmarkt.password is None
    _mock_tfl({"490000123W": BUS_STOP_JSON}, {"490000123W": BUS_ARRIVALS_JSON})
    loop = _build_loop(config, monkeypatch)
    shown = _spy_on_display_screen(loop, monkeypatch)

    _run_cycles(loop, monkeypatch)

    assert _calls_to("https://api.glowmarkt.com") == 0
    assert loop.api_reg.clients["glowmarkt"].is_disabled()
    assert shown[0]["glowmarkt"] is None
    assert len(shown[0]["tfl"].arrival_panels) == 1


@responses.activate
def test_full_render_cycle_with_spotify_track(isolated_cwd, monkeypatch):
    config = _make_config()
    config.tfl.stop_ids = ["490000123W"]
    config.spotify.enabled = True
    _mock_tfl_and_glowmarkt({"490000123W": BUS_STOP_JSON}, {"490000123W": BUS_ARRIVALS_JSON})
    responses.add(responses.GET, NOW_PLAYING_URL, json=TRACK_JSON)
    responses.add(responses.GET, "https://example.com/album.jpg", body=_png_bytes(), content_type="image/png")
    loop = _build_loop(config, monkeypatch)
    shown = _spy_on_display_screen(loop, monkeypatch)

    _run_cycles(loop, monkeypatch)

    assert isinstance(shown[0]["spotify"], SpotifyPanel)
    assert shown[0]["spotify"].playingRightNow.song == "Test Song"
    assert _calls_to("https://example.com/album.jpg") == 1  # the screen really was rendered with the art


@responses.activate
def test_full_render_cycle_when_nothing_is_playing(isolated_cwd, monkeypatch):
    config = _make_config()
    config.tfl.stop_ids = ["490000123W"]
    config.spotify.enabled = True
    _mock_tfl_and_glowmarkt({"490000123W": BUS_STOP_JSON}, {"490000123W": BUS_ARRIVALS_JSON})
    responses.add(responses.GET, NOW_PLAYING_URL, body="null", content_type="application/json")
    loop = _build_loop(config, monkeypatch)
    shown = _spy_on_display_screen(loop, monkeypatch)

    _run_cycles(loop, monkeypatch)

    assert shown[0]["spotify"] is None
    assert isinstance(shown[0]["glowmarkt"], EnergyPanel)


@responses.activate
def test_full_render_cycle_with_weather(isolated_cwd, monkeypatch):
    config = _make_config()
    config.weather.location = "London"
    responses.add(
        responses.GET,
        "https://geocoding-api.open-meteo.com/v1/search",
        json={"results": [{"name": "London", "latitude": 51.5, "longitude": -0.12}]},
    )
    responses.add(
        responses.GET,
        "https://api.open-meteo.com/v1/forecast",
        json={
            "current": {"temperature_2m": 14.2, "weather_code": 2, "is_day": 1},
            "daily": {
                "temperature_2m_max": [18.4],
                "temperature_2m_min": [9.1],
                "precipitation_probability_max": [40],
            },
        },
    )
    _mock_glowmarkt()
    loop = _build_loop(config, monkeypatch)
    shown = _spy_on_display_screen(loop, monkeypatch)

    _run_cycles(loop, monkeypatch)

    assert isinstance(shown[0]["weather"], WeatherPanel)
    assert shown[0]["weather"].weather.temperature == 14.2


@responses.activate
def test_one_api_being_down_does_not_stop_the_others_reaching_the_screen(isolated_cwd, monkeypatch):
    config = _make_config()
    config.tfl.stop_ids = ["490000123W"]
    responses.add(responses.GET, "https://api.tfl.gov.uk/StopPoint/490000123W", status=500)
    _mock_glowmarkt()
    loop = _build_loop(config, monkeypatch)
    shown = _spy_on_display_screen(loop, monkeypatch)

    _run_cycles(loop, monkeypatch)

    assert len(shown) == 1
    assert shown[0].get("tfl") is None  # no stops could be resolved, so nothing to show
    assert isinstance(shown[0]["glowmarkt"], EnergyPanel)


@responses.activate
def test_later_cycles_reuse_client_state_and_keep_slow_panels_on_screen(isolated_cwd, monkeypatch):
    """Clients live for the whole run: Glowmarkt polls every 15 minutes, so the second
    (seconds-later) cycle must not re-authenticate or refetch -- but the energy panel
    still has to be drawn. Same for TfL, which polls every minute and isn't due yet
    either: its last panel carries over rather than blanking the screen."""
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
    loop = _build_loop(config, monkeypatch)
    shown = _spy_on_display_screen(loop, monkeypatch)

    _run_cycles(loop, monkeypatch, cycles=2)

    assert len(shown) == 2
    assert _calls_to(f"{GLOWMARKT_URL}/auth") == 1
    assert _calls_to(f"{GLOWMARKT_URL}/virtualentity") == 1
    assert _calls_to(f"{GLOWMARKT_URL}/resource") == 1  # not due again yet
    assert shown[1]["glowmarkt"] is shown[0]["glowmarkt"]
    assert shown[1]["tfl"] is shown[0]["tfl"]


@responses.activate
def test_run_shows_pairing_screen_and_skips_normal_display_while_unpaired(isolated_cwd, monkeypatch):
    """While a pairing code is active, run() shouldn't fetch anything or paint the
    normal screen. A device that's still unpaired has an empty config (nothing set up
    on the broker yet), so no client has any reason to make a request either -- and
    none are mocked here, so one that did would raise ConnectionError."""
    loop = _build_loop(make_config(), monkeypatch, pairing_code="ABC123")
    shown = _spy_on_display_screen(loop, monkeypatch)
    pairing_screens = []
    monkeypatch.setattr(
        loop.display,
        "display_pairing_screen",
        lambda panel: pairing_screens.append((panel.pairing_code, panel.device_id)),
    )

    _run_cycles(loop, monkeypatch)

    assert pairing_screens == [("ABC123", "test-device")]
    assert shown == []
    assert loop.api_reg.panels == {}
    assert len(responses.calls) == 0


@responses.activate
def test_run_only_repaints_pairing_screen_when_code_changes(isolated_cwd, monkeypatch):
    """A full e-paper refresh is slow and visibly flashy -- repainting an unchanged
    pairing code every cycle for however long a device sits unpaired would be
    needless wear, not just noise. Unlike the test above, /config IS mocked here
    (always returning the same code) so refresh_broker_config() actually re-derives
    pairing_code_panel each cycle via BrokerClient's cache, instead of leaving the
    cycle-1 panel (and its has_changed=True) untouched forever."""
    responses.add(
        responses.GET,
        f"{TEST_BROKER_URL}/api/devices/test-device/config",
        json=_app_config_json(pairing_code="ABC123"),
    )
    loop = _build_loop(make_config(), monkeypatch, pairing_code="ABC123")
    screens_shown = []
    monkeypatch.setattr(loop.display, "display_pairing_screen", lambda panel: screens_shown.append(panel.pairing_code))

    # cycle 1: pairing_code_panel seeded by _build_loop, has_changed=True -> repaint
    # cycle 2: refresh_broker_config() re-fetched the same code -> has_changed=False -> no repaint
    _run_cycles(loop, monkeypatch, cycles=2)

    assert screens_shown == ["ABC123"]


@responses.activate
def test_refresh_broker_config_applies_the_new_interval_and_pairing_state(isolated_cwd, monkeypatch):
    responses.add(
        responses.GET,
        f"{TEST_BROKER_URL}/api/devices/test-device/config",
        json=_app_config_json(pairing_code=None, interval=42),
    )
    loop = _build_loop(make_config(), monkeypatch, pairing_code="ABC123")

    asyncio.run(loop.refresh_broker_config())

    assert loop.interval == 42
    assert loop.config.interval == 42
    assert loop.pairing_code_panel.pairing_code is None  # the device just got paired
    assert loop.pairing_code_panel.has_changed is True


@responses.activate
def test_config_changes_from_the_broker_reach_the_screen_on_the_next_cycle(isolated_cwd, monkeypatch):
    """The device boots with nothing set up; the owner then adds a stop on the broker.
    Cycle 2 must pick that up without a restart."""
    _mock_tfl({"490000123W": BUS_STOP_JSON}, {"490000123W": BUS_ARRIVALS_JSON})
    new_config = _app_config_json()
    new_config["tfl"]["stop_ids"] = ["490000123W"]
    responses.add(responses.GET, f"{TEST_BROKER_URL}/api/devices/test-device/config", json=new_config)
    loop = _build_loop(make_config(), monkeypatch)
    shown = _spy_on_display_screen(loop, monkeypatch)

    _run_cycles(loop, monkeypatch, cycles=2)

    assert shown[0].get("tfl") is None
    assert len(shown[1]["tfl"].arrival_panels) == 1


@responses.activate
def test_the_first_cycle_reports_how_long_startup_took_once(isolated_cwd, monkeypatch, capsys):
    responses.add(
        responses.GET,
        f"{TEST_BROKER_URL}/api/devices/test-device/config",
        json=_app_config_json(pairing_code="ABC123"),
    )
    loop = _build_loop(make_config(), monkeypatch, pairing_code="ABC123")
    monkeypatch.setattr(loop.display, "display_pairing_screen", lambda panel: None)

    _run_cycles(loop, monkeypatch, cycles=2)

    assert capsys.readouterr().out.count("First cycle finished") == 1


MISSING_BOTH = ["a weather location", "a bus or tube stop"]


def _spy_on_setup_screen(loop: DisplayLoop, monkeypatch) -> list[list[str]]:
    seen: list[list[str]] = []
    monkeypatch.setattr(loop.display, "display_setup_screen", lambda panel: seen.append(list(panel.missing)))
    return seen


def _mock_config(**kwargs) -> None:
    responses.add(responses.GET, f"{TEST_BROKER_URL}/api/devices/test-device/config", json=_app_config_json(**kwargs))


@responses.activate
def test_run_shows_the_setup_checklist_once_and_leaves_the_apis_alone_until_set_up(isolated_cwd, monkeypatch):
    _mock_config(setup_missing=MISSING_BOTH)
    loop = _build_loop(make_config(setup_missing=MISSING_BOTH), monkeypatch)
    shown = _spy_on_display_screen(loop, monkeypatch)
    setup_screens = _spy_on_setup_screen(loop, monkeypatch)

    _run_cycles(loop, monkeypatch, cycles=2)

    assert setup_screens == [MISSING_BOTH]
    assert shown == []
    assert loop.api_reg.panels == {}


@responses.activate
def test_run_moves_on_to_the_dashboard_once_setup_is_complete(isolated_cwd, monkeypatch):
    _mock_config(setup_missing=[])
    loop = _build_loop(make_config(setup_missing=MISSING_BOTH), monkeypatch)
    shown = _spy_on_display_screen(loop, monkeypatch)
    setup_screens = _spy_on_setup_screen(loop, monkeypatch)

    _run_cycles(loop, monkeypatch, cycles=2)

    assert setup_screens == [MISSING_BOTH]
    assert len(shown) == 1


@responses.activate
def test_a_pairing_code_takes_precedence_over_the_setup_checklist(isolated_cwd, monkeypatch):
    loop = _build_loop(make_config(setup_missing=MISSING_BOTH), monkeypatch, pairing_code="ABC123")
    setup_screens = _spy_on_setup_screen(loop, monkeypatch)
    pairing_screens = []
    monkeypatch.setattr(
        loop.display, "display_pairing_screen", lambda panel: pairing_screens.append(panel.pairing_code)
    )

    _run_cycles(loop, monkeypatch)

    assert pairing_screens == ["ABC123"]
    assert setup_screens == []


@responses.activate
@pytest.mark.parametrize(
    ("pairing_code", "setup_missing", "stage"),
    [("ABC123", MISSING_BOTH, "pairing"), (None, MISSING_BOTH, "setup"), (None, [], "running")],
    ids=["pairing", "setup", "dashboard"],
)
def test_run_reports_the_stage_it_is_in(isolated_cwd, monkeypatch, pairing_code, setup_missing, stage):
    _mock_config(pairing_code=pairing_code, setup_missing=setup_missing)
    loop = _build_loop(make_config(setup_missing=setup_missing), monkeypatch, pairing_code=pairing_code)

    _run_cycles(loop, monkeypatch)

    assert loop.api_reg.status.stage == stage


def _record_publishes(loop: DisplayLoop, monkeypatch) -> list[bool]:
    forced: list[bool] = []

    async def publish_health(force: bool = False) -> None:
        forced.append(force)

    monkeypatch.setattr(loop.api_reg, "publish_health", publish_health)
    return forced


@responses.activate
def test_run_publishes_health_every_cycle_and_forces_it_only_when_the_stage_changes(isolated_cwd, monkeypatch):
    _mock_config(pairing_code="ABC123")
    loop = _build_loop(make_config(), monkeypatch, pairing_code="ABC123")
    forced = _record_publishes(loop, monkeypatch)

    _run_cycles(loop, monkeypatch, cycles=2)

    assert forced == [True, False]  # waiting_for_broker -> pairing, then no change


@responses.activate
def test_run_forces_a_publish_when_setup_completes(isolated_cwd, monkeypatch):
    _mock_config(setup_missing=[])
    loop = _build_loop(make_config(setup_missing=MISSING_BOTH), monkeypatch)
    forced = _record_publishes(loop, monkeypatch)

    _run_cycles(loop, monkeypatch, cycles=2)

    assert forced == [True, True]  # -> setup, then -> running


@responses.activate
def test_refreshing_the_config_records_when_the_broker_last_answered(isolated_cwd, monkeypatch):
    _mock_config()
    loop = _build_loop(make_config(), monkeypatch)
    assert loop.api_reg.status.last_broker_sync is None

    _run_cycles(loop, monkeypatch, cycles=2)

    assert loop.api_reg.status.last_broker_sync is not None


@responses.activate
def test_the_setup_checklist_is_repainted_when_the_list_changes(isolated_cwd, monkeypatch):
    _mock_config(setup_missing=["a bus or tube stop"])
    loop = _build_loop(make_config(setup_missing=MISSING_BOTH), monkeypatch)
    setup_screens = _spy_on_setup_screen(loop, monkeypatch)

    _run_cycles(loop, monkeypatch, cycles=2)

    assert setup_screens == [MISSING_BOTH, ["a bus or tube stop"]]
