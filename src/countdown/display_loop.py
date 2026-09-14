import time

import pydantic
import requests

from countdown.glow_client import GlowClient
from countdown.tfl_client import TflClient
from countdown.spotify_client import SpotifyClient
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

    def __init__(self, config: AppConfig, display = DisplayController()):
        self.config = config
        self.interval = config.interval
        self.display = display
        self.tfl = TflClient(config.tfl)
        self.glow = GlowClient(config)
        self.spotify = SpotifyClient(config.spotify)
        self.weather = WeatherClient(config.weather)
        self.resource_id = self.glow.get_electricity_resource_id()
        self.energy = {"day": None, "month": None, "year": None}
        self.current_track: dict | None = None
        self.weather_panel = None
        self.page_count = 1
        self.page = 0

    def run(self) -> None:
        while True:
            try:
                self.page_count = self.tfl.init()
                arrival_panel = CombinedArrivalPanel(self.tfl.get_next_arrivals())
                if self.page % self.page_count == 0:
                    self.energy["day"] = safe_fetch(lambda: self.glow.get_day_readings(self.resource_id), self.energy["day"])
                    self.energy["month"] = safe_fetch(lambda: self.glow.get_month_readings(self.resource_id), self.energy["month"])
                    self.energy["year"] = safe_fetch(lambda: self.glow.get_year_readings(self.resource_id), self.energy["year"])
                    energy_panel = EnergyPanel(self.energy["day"], self.energy["month"], self.energy["year"])
                    self.current_track = self.spotify.get_current_track()
                    self.weather_panel = safe_fetch(lambda: self.weather.get_weather(), self.weather_panel)
                    self.display.display_screen(arrival_panel, energy_panel, self.current_track, self.weather_panel)
                else:
                    energy_panel = EnergyPanel(self.energy["day"], self.energy["month"], self.energy["year"])
                    self.display.display_partial(arrival_panel, energy_panel, self.current_track, self.weather_panel)
            except requests.exceptions.RequestException as e:
                print(f"Network error encountered: {e}")
            except Exception as e:
                print(f"Unexpected error: {e}")

            time.sleep(self.interval)
            self.reload_config_if_changed()

            self.page += 1
            if self.page % self.page_count == 0:
                self.page = 0

            if not self.interval:
                break

    def reload_config_if_changed(self) -> None:
        """Building a fresh TflClient can never fail: construction does no network
        I/O, and stop resolution is retried lazily (and safely) on next use."""
        if config_manager.has_changed():
            self.config = config_manager.load_config()
            self.tfl = TflClient(self.config.tfl)
