import time

import pydantic
import requests

from countdown.glow_client import GlowClient
from countdown.tfl_client import TflClient
from countdown.broker_client import BrokerClient
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
        self.broker = BrokerClient(config.broker_url)
        self.weather = WeatherClient(config.weather)
        self.resource_id = self.glow.get_electricity_resource_id()
        self.energy = {"day": None, "month": None, "year": None}
        self.current_track: dict | None = None
        self.weather_panel = None
        self.page_count = 1
        self.page = 0

        if self.broker.pairing_code:
            self.display.display_pairing_screen(self.broker.pairing_code, self.broker.device_id)

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
                    # The broker already gates this on spotify.enabled server-side, so
                    # there's no local check to duplicate here (and no race on cycle 1
                    # before refresh_broker_config has synced that flag from the server).
                    self.current_track = safe_fetch(lambda: self.broker.get_current_track(), self.current_track)
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
            self.refresh_broker_config()

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

    def refresh_broker_config(self) -> None:
        """Polls the broker's per-device config every cycle -- it's the only way to
        find out something changed, since the broker exposes no change-timestamp.
        Only mutates/rebuilds what actually differs, same principle as
        reload_config_if_changed only rebuilding tfl when has_changed() is true --
        rebuilding TflClient unconditionally would force needless stop-resolution
        calls against the TfL API every cycle for no reason."""
        fetched = safe_fetch(lambda: self.broker.get_config(), None)
        if fetched is None:
            return

        if (fetched.tfl.app_key, fetched.tfl.stop_ids) != (self.config.tfl.app_key, self.config.tfl.stop_ids):
            self.config.tfl.app_key = fetched.tfl.app_key
            self.config.tfl.stop_ids = fetched.tfl.stop_ids
            self.tfl = TflClient(self.config.tfl)

        if (fetched.weather.api_key, fetched.weather.location) != (self.config.weather.api_key, self.config.weather.location):
            self.config.weather.api_key = fetched.weather.api_key
            self.config.weather.location = fetched.weather.location
            self.weather = WeatherClient(self.config.weather)

        self.config.interval = fetched.interval
        self.interval = fetched.interval
        self.config.spotify.enabled = fetched.spotify.enabled
