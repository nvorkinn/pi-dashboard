import datetime as dt
import pickle
from pathlib import Path

from pyowm import OWM
from pyowm.weatherapi30.weather import Weather

from countdown.config_manager import WeatherConfig
from display.weather_panel import WeatherPanel

CACHE_FILE = Path("weather_cache.pkl")


class WeatherClient:
    def __init__(self, config: WeatherConfig):
        self.owm = OWM(config.api_key)
        self.mgr = self.owm.weather_manager()
        self.location = config.location
        self.weather: Weather | None = None
        self.rec_time: int | None = None

    def get_weather(self) -> WeatherPanel:
        # Load from local cache during development if present
        if CACHE_FILE.exists():
            with open(CACHE_FILE, "rb") as f:
                self.weather = pickle.load(f)
            return WeatherPanel(self.weather)

        # In-memory throttle check if caching file is not used
        if self.weather and self.rec_time:
            last_poll = dt.datetime.fromtimestamp(self.rec_time)
            if dt.datetime.now() - dt.timedelta(minutes=30) < last_poll:
                return WeatherPanel(self.weather)

        print("Fetching fresh weather from live OWM API...")
        observation = self.mgr.weather_at_place(self.location)
        self.weather = observation.weather
        self.rec_time = observation.rec_time

        # Save to local cache for future development runs
        with open(CACHE_FILE, "wb") as f:
            pickle.dump(self.weather, f)
        print(f"Saved live weather response to {CACHE_FILE}")

        return WeatherPanel(self.weather)
