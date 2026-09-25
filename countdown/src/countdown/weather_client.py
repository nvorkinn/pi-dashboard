import datetime as dt
import logging

from countdown.abstract_client import AbstractClient
from countdown.config_manager import WeatherConfig
from countdown.http import DEFAULT_TIMEOUT
from countdown.models import ForecastResponse, GeocodingResponse, Weather
from display.panel import Panel
from display.weather_panel import WeatherPanel

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Forecasts move slowly; the display loop runs every few seconds
REFRESH_INTERVAL = dt.timedelta(minutes=30)


class WeatherClient(AbstractClient):
    """Current conditions plus today's outlook from Open-Meteo (keyless, so
    WeatherConfig.api_key is unused). Construction never touches the network: the
    location is geocoded lazily on first fetch, and only once."""

    panel_title = "Weather"

    def __init__(self, config: WeatherConfig):
        super().__init__(config)
        self.location = config.location
        self._coordinates: tuple[float, float] | None = None
        self._panel: Panel | None = None
        self._last_attempt: dt.datetime | None = None

    def _initialise(self) -> None:
        pass

    def needs_refresh(self, new_config: WeatherConfig) -> bool:
        # Open-Meteo is keyless, so api_key changing changes nothing.
        return self.location != new_config.location

    def _update(self) -> Panel:
        """A MessagePanel when there's nothing to show: no location configured, or one
        Open-Meteo couldn't find. Network/parse failures raise instead (RequestException /
        ValidationError), for safe_fetch to fall back to the last good panel."""
        if not self.location:
            return self.message_panel("No location set")

        if self._last_attempt and dt.datetime.now() - self._last_attempt < REFRESH_INTERVAL:
            return self._panel

        coordinates = self._geocode()
        if coordinates is None:
            logger.warning(f"Could not find a location matching {self.location!r} on Open-Meteo")
            self._panel = self.message_panel("Location not found")
        else:
            self._panel = WeatherPanel(self._fetch_forecast(*coordinates))
        self._last_attempt = dt.datetime.now()
        return self._panel

    def _geocode(self) -> tuple[float, float] | None:
        if self._coordinates is None:
            response = self.session.get(
                GEOCODING_URL, params={"name": self.location, "count": 1, "format": "json"}, timeout=DEFAULT_TIMEOUT
            )
            response.raise_for_status()
            results = GeocodingResponse.model_validate(response.json()).results
            if results:
                self._coordinates = (results[0].latitude, results[0].longitude)
        return self._coordinates

    def _fetch_forecast(self, latitude: float, longitude: float) -> Weather:
        response = self.session.get(
            FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,weather_code,is_day",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",  # so "today" is the location's today, not UTC's
                "forecast_days": 1,
            },
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        forecast = ForecastResponse.model_validate(response.json())
        return Weather(
            temperature=forecast.current.temperature,
            weather_code=forecast.current.weather_code,
            is_day=forecast.current.is_day,
            high=forecast.daily.temperature_max[0],
            low=forecast.daily.temperature_min[0],
            precipitation_probability=forecast.daily.precipitation_probability_max[0],
        )
