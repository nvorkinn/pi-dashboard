import time

import pydantic
import requests

from countdown.glow_client import GlowClient
from countdown.tfl_client import TflClient
from countdown.broker_client import BrokerClient
from countdown.config_manager import AppConfig
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

    def __init__(self, broker_url: str, display = DisplayController(), live: AppConfig | None = None):
        self.live = live if live is not None else AppConfig()
        self.interval = self.live.interval
        self.display = display
        self.tfl = TflClient(self.live.tfl)
        self.glow = GlowClient(self.live.glowmarkt)
        self.broker = BrokerClient(broker_url)
        self.weather = WeatherClient(self.live.weather)
        # Unlike tfl/weather, Glowmarkt credentials aren't known until the first
        # broker sync completes (no local .env fallback any more) -- resolving this
        # eagerly here would fail on every single restart, not just first boot. So
        # it's looked up lazily in run(), retried each full-refresh cycle via
        # safe_fetch, same as the day/month/year readings that depend on it.
        self.resource_id: str | None = None
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
                    # Most gifted devices never get Glowmarkt set up on the broker at
                    # all -- username/password come back None, not omitted, so this
                    # is the normal case for most devices, not a failure to recover
                    # from. Skip attempting auth entirely rather than hitting
                    # Glowmarkt with known-missing credentials every cycle forever.
                    have_glowmarkt_creds = self.live.glowmarkt.username and self.live.glowmarkt.password
                    if self.resource_id is None and have_glowmarkt_creds:
                        self.resource_id = safe_fetch(lambda: self.glow.get_electricity_resource_id(), None)
                    if self.resource_id is not None:
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
            self.refresh_broker_config()

            self.page += 1
            if self.page % self.page_count == 0:
                self.page = 0

            if not self.interval:
                break

    def refresh_broker_config(self) -> None:
        """Polls the broker's per-device config every cycle -- it's the only way to
        find out something changed, since the broker exposes no change-timestamp.
        Only mutates/rebuilds what actually differs (building a fresh TflClient can
        never fail: construction does no network I/O, stop resolution is retried
        lazily and safely on next use -- but it would force needless stop-resolution
        calls against the TfL API every cycle if rebuilt unconditionally)."""
        fetched = safe_fetch(lambda: self.broker.get_config(), None)
        if fetched is None:
            return

        if (fetched.tfl.app_key, fetched.tfl.stop_ids) != (self.live.tfl.app_key, self.live.tfl.stop_ids):
            self.live.tfl.app_key = fetched.tfl.app_key
            self.live.tfl.stop_ids = fetched.tfl.stop_ids
            self.tfl = TflClient(self.live.tfl)

        if (fetched.weather.api_key, fetched.weather.location) != (self.live.weather.api_key, self.live.weather.location):
            self.live.weather.api_key = fetched.weather.api_key
            self.live.weather.location = fetched.weather.location
            self.weather = WeatherClient(self.live.weather)

        if (fetched.glowmarkt.username, fetched.glowmarkt.password) != (self.live.glowmarkt.username, self.live.glowmarkt.password):
            self.live.glowmarkt.username = fetched.glowmarkt.username
            self.live.glowmarkt.password = fetched.glowmarkt.password
            self.glow = GlowClient(self.live.glowmarkt)
            self.resource_id = None  # force re-lookup against the new credentials

        self.live.interval = fetched.interval
        self.interval = fetched.interval
        self.live.spotify.enabled = fetched.spotify.enabled
