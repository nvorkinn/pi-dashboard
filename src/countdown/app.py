import signal
import sys
import threading
import time
from dataclasses import dataclass, field

import pydantic
import requests

from countdown.glow_client import GlowClient
from countdown.tfl_client import TflClient
from countdown.spotify_client import SpotifyClient
from countdown.flask import app
from countdown.config_manager import config_manager
from countdown.weather_client import WeatherClient
from display.combined_arrival_panel import CombinedArrivalPanel
from display.display import DisplayController
from display.energy_panel import EnergyPanel

def safe_fetch(func, fallback):
    try:
        return func()
    except requests.exceptions.RequestException as e:
        print(f"Exception with API call to Glowmarkt: {e}")
        return fallback
    except pydantic.ValidationError as e:
        print(f"Pydantic validation error: {e}")
        return fallback


@dataclass
class DisplayState:
    """Holds everything that needs to survive between refresh cycles -- last-known
    panels (so a failed fetch can keep showing stale-but-valid data) and the current
    page for cycling through stops."""
    page: int = 0
    energy: dict = field(default_factory=lambda: {"day": None, "month": None, "year": None})
    energy_panel: EnergyPanel | None = None
    current_track: dict | None = None
    weather_panel: object | None = None


def run_display_cycle(
    display: DisplayController,
    tfl: TflClient,
    glow: GlowClient,
    resource_id: str,
    spotify: SpotifyClient,
    weather: WeatherClient,
    state: DisplayState,
) -> int:
    """Render and push exactly one refresh cycle, mutating `state` in place with
    whatever succeeded. Returns the current page count. Deliberately does not catch
    anything itself -- the caller decides how to handle a cycle that failed outright."""
    # Cheap: a no-op once stops are resolved, and self-heals by retrying setup here
    # if an earlier attempt (initial or after a config change) failed.
    page_count = tfl.get_page_count()
    arrival_panel = CombinedArrivalPanel(tfl.get_next_arrivals())
    if state.page % page_count == 0:
        state.energy["day"] = safe_fetch(lambda: glow.get_day_readings(resource_id), state.energy["day"])
        state.energy["month"] = safe_fetch(lambda: glow.get_month_readings(resource_id), state.energy["month"])
        state.energy["year"] = safe_fetch(lambda: glow.get_year_readings(resource_id), state.energy["year"])
        state.energy_panel = EnergyPanel(state.energy["day"], state.energy["month"], state.energy["year"])
        state.current_track = spotify.get_current_track()
        state.weather_panel = safe_fetch(lambda: weather.get_weather(), state.weather_panel)
        display.display_screen(arrival_panel, state.energy_panel, state.current_track, state.weather_panel)
    else:
        display.display_partial(arrival_panel, state.energy_panel, state.current_track, state.weather_panel)
    return page_count


def main() -> None:
    config = config_manager.load_config()
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=config.config_port),
        daemon=True
    )
    flask_thread.start()
    display = DisplayController()
    # Setup graceful signal handling
    def handle_shutdown(_signum, _frame):
        print("\nShutting down gracefully...")
        # Put your epaper display to sleep to prevent burn-in
        display.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    tfl = TflClient(config.tfl)
    glow = GlowClient(config)
    spotify = SpotifyClient(config.spotify)
    weather = WeatherClient(config.weather)
    resource_id = glow.get_electricity_resource_id()
    state = DisplayState()
    page_count = 1
    while True:
        try:
            page_count = run_display_cycle(display, tfl, glow, resource_id, spotify, weather, state)
        except requests.exceptions.RequestException as e:
            print(f"Network error encountered: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

        time.sleep(config.interval)

        if config_manager.has_changed():
            # Building a fresh TflClient can never fail: construction does no network
            # I/O, and stop resolution is retried lazily (and safely) on next use.
            config = config_manager.load_config()
            tfl = TflClient(config.tfl)

        state.page += 1
        if state.page == page_count:
            state.page = 0
