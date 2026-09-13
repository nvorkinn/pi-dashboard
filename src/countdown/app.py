import signal
import sys
import threading
import time

import pydantic
import requests

from countdown.glow_client import GlowClient
from countdown.tfl_client import TflClient
from countdown.spotify_client import SpotifyClient
from countdown.flask import app
from countdown.config_manager import AppConfig, config_manager
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


class DisplayLoop:
    """Owns everything needed to run one refresh cycle, plus everything that needs to
    survive between cycles -- last-known energy readings/track/weather panel, so a
    failed fetch can keep showing stale-but-valid data instead of nothing. EnergyPanel
    itself isn't cached: it's cheap to build (no I/O, no rendering happens until
    display.py calls .render()), so it's rebuilt on demand from self.energy rather
    than kept as separate, redundant state -- current_track already works this way."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.display = DisplayController()
        self.tfl = TflClient(config.tfl)
        self.glow = GlowClient(config)
        self.spotify = SpotifyClient(config.spotify)
        self.weather = WeatherClient(config.weather)
        self.resource_id = self.glow.get_electricity_resource_id()
        self.energy = {"day": None, "month": None, "year": None}
        self.current_track: dict | None = None
        self.weather_panel = None
        self.page = 0

    def run_cycle(self) -> int:
        """Render and push exactly one refresh cycle. Returns the current page count.
        Deliberately does not catch anything itself -- the caller decides how to
        handle a cycle that failed outright."""
        # Cheap: a no-op once stops are resolved, and self-heals by retrying setup
        # here if an earlier attempt (initial or after a config change) failed.
        page_count = self.tfl.get_page_count()
        arrival_panel = CombinedArrivalPanel(self.tfl.get_next_arrivals())
        if self.page % page_count == 0:
            self.energy["day"] = safe_fetch(lambda: self.glow.get_day_readings(self.resource_id), self.energy["day"])
            self.energy["month"] = safe_fetch(lambda: self.glow.get_month_readings(self.resource_id), self.energy["month"])
            self.energy["year"] = safe_fetch(lambda: self.glow.get_year_readings(self.resource_id), self.energy["year"])
            self.current_track = self.spotify.get_current_track()
            self.weather_panel = safe_fetch(lambda: self.weather.get_weather(), self.weather_panel)
            energy_panel = EnergyPanel(self.energy["day"], self.energy["month"], self.energy["year"])
            self.display.display_screen(arrival_panel, energy_panel, self.current_track, self.weather_panel)
        else:
            energy_panel = EnergyPanel(self.energy["day"], self.energy["month"], self.energy["year"])
            self.display.display_partial(arrival_panel, energy_panel, self.current_track, self.weather_panel)
        return page_count

    def reload_config_if_changed(self) -> None:
        """Building a fresh TflClient can never fail: construction does no network
        I/O, and stop resolution is retried lazily (and safely) on next use."""
        if not config_manager.has_changed():
            return
        self.config = config_manager.load_config()
        self.tfl = TflClient(self.config.tfl)


def main() -> None:
    config = config_manager.load_config()
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=config.config_port),
        daemon=True
    )
    flask_thread.start()
    loop = DisplayLoop(config)

    # Setup graceful signal handling
    def handle_shutdown(_signum, _frame):
        print("\nShutting down gracefully...")
        # Put your epaper display to sleep to prevent burn-in
        loop.display.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    page_count = 1
    while True:
        try:
            page_count = loop.run_cycle()
        except requests.exceptions.RequestException as e:
            print(f"Network error encountered: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

        time.sleep(loop.config.interval)
        loop.reload_config_if_changed()

        loop.page += 1
        if loop.page == page_count:
            loop.page = 0
