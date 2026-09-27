from pydantic import BaseModel, Field


class GeocodingResult(BaseModel):
    latitude: float
    longitude: float
    name: str


class GeocodingResponse(BaseModel):
    # Open-Meteo leaves "results" out entirely (rather than sending []) when nothing matches
    results: list[GeocodingResult] = []


class CurrentConditions(BaseModel):
    temperature: float = Field(alias="temperature_2m")
    weather_code: int  # WMO code, see display.weather_panel.ICON_MAP
    is_day: bool


class DailyForecast(BaseModel):
    """Open-Meteo returns one parallel list per variable, one entry per day (today first)."""

    temperature_max: list[float] = Field(alias="temperature_2m_max")
    temperature_min: list[float] = Field(alias="temperature_2m_min")
    precipitation_probability_max: list[int | None]


class ForecastResponse(BaseModel):
    current: CurrentConditions
    daily: DailyForecast


class Weather(BaseModel):
    """What the weather panel shows: right now, plus today's outlook."""

    temperature: float
    weather_code: int
    is_day: bool
    high: float
    low: float
    precipitation_probability: int | None = None
