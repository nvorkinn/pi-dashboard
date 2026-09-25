from abc import ABC
from datetime import timedelta
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field, HttpUrl, field_validator


class Mode(StrEnum):
    BUS = "bus"
    TUBE = "tube"
    NATIONAL_RAIL = "national-rail"
    INTERNATIONAL_RAIL = "international-rail"


readings_type = tuple[list[float] | None, list[float] | None, list[float] | None]


class Arrival(BaseModel, ABC):
    naptan_id: str = Field(alias="naptanId")
    line: str = Field(alias="lineName")
    time_to_station: int = Field(alias="timeToStation")


class TubeArrival(Arrival):
    mode_name: Literal[Mode.TUBE] = Field(alias="modeName")
    towards: str
    destination_naptan_id: str | None = Field(alias="destinationNaptanId", default=None)


class BusArrival(Arrival):
    mode_name: Literal[Mode.BUS] = Field(alias="modeName")
    destination: str = Field(alias="destinationName")

    @field_validator("destination")
    @classmethod
    def trim_destination(cls, value: str) -> str:
        """TfL often qualifies a destination after a comma (a road or landmark), which
        doesn't fit on the panel and isn't needed to tell buses apart. Keeps the whole
        name if there's nothing before the comma."""
        return value.split(",", 1)[0].strip() or value.strip()


ArrivalUnion = Annotated[BusArrival | TubeArrival, Field(discriminator="mode_name")]


class AdditionalProperty(BaseModel):
    key: str
    value: str


class StopType(StrEnum):
    NAPTAN_ONSTREET_BUS_COACH_STOP_PAIR = "NaptanOnstreetBusCoachStopPair"
    NAPTAN_PUBLIC_BUS_COACH_TRAM = "NaptanPublicBusCoachTram"
    NAPTAN_BUS_COACH_STATION = "NaptanBusCoachStation"
    TRANSPORT_INTERCHANGE = "TransportInterchange"
    NAPTAN_ONSTREET_BUS_COACH_STOP_CLUSTER = "NaptanOnstreetBusCoachStopCluster"
    NAPTAN_RAIL_STATION = "NaptanRailStation"
    NAPTAN_METRO_STATION = "NaptanMetroStation"
    NAPTAN_RAIL_ENTRANCE = "NaptanRailEntrance"
    NAPTAN_RAIL_ACCESS_AREA = "NaptanRailAccessArea"
    NAPTAN_METRO_ENTRANCE = "NaptanMetroEntrance"
    NAPTAN_METRO_ACCESS_AREA = "NaptanMetroAccessArea"
    NAPTAN_METRO_PLATFORM = "NaptanMetroPlatform"


class StopPoint(BaseModel):
    naptan_id: str = Field(alias="naptanId")
    common_name: str = Field(alias="commonName")
    modes: list[Mode]
    additional_properties: list[AdditionalProperty] = Field(alias="additionalProperties")
    children: list[StopPointUnion] = []


class OtherStopPoint(StopPoint):
    stop_type: Literal[
        StopType.NAPTAN_ONSTREET_BUS_COACH_STOP_PAIR,
        StopType.TRANSPORT_INTERCHANGE,
        StopType.NAPTAN_ONSTREET_BUS_COACH_STOP_CLUSTER,
        StopType.NAPTAN_RAIL_STATION,
        StopType.NAPTAN_RAIL_ENTRANCE,
        StopType.NAPTAN_RAIL_ACCESS_AREA,
        StopType.NAPTAN_METRO_ENTRANCE,
        StopType.NAPTAN_METRO_ACCESS_AREA,
        StopType.NAPTAN_METRO_PLATFORM,
        StopType.NAPTAN_BUS_COACH_STATION,
    ] = Field(alias="stopType")


class SingleStopPoint(StopPoint):
    stop_type: Literal[StopType.NAPTAN_PUBLIC_BUS_COACH_TRAM] = Field(alias="stopType")
    stop_letter: str = Field(alias="stopLetter")


class MetroStopPoint(StopPoint):
    stop_type: Literal[StopType.NAPTAN_METRO_STATION] = Field(alias="stopType")


StopPointUnion = Annotated[OtherStopPoint | SingleStopPoint | MetroStopPoint, Field(discriminator="stop_type")]


class StopPointResponse(BaseModel):
    stop_points: list[StopPoint] = Field(alias="stopPoints")


class Resource(BaseModel):
    name: str
    resourceId: str


class Entity(BaseModel):
    resources: list[Resource]


class Readings(BaseModel):
    data: list[tuple[int, float]]


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


MillisecondTimedelta = Annotated[
    timedelta, BeforeValidator(lambda v: timedelta(milliseconds=v) if isinstance(v, (int, float)) else v)
]


class Image(BaseModel):
    width: int
    height: int
    url: HttpUrl


class Album(BaseModel):
    images: list[Image]
    name: str
    # release_date: date


class Artist(BaseModel):
    name: str


class Track(BaseModel):
    album: Album
    artists: list[Artist]
    name: str
    duration_ms: MillisecondTimedelta


class Queue(BaseModel):
    currently_playing: Track | None
    queue: list[Track]
