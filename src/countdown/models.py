from abc import ABC
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


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

ArrivalUnion = Annotated[
    BusArrival | TubeArrival,
    Field(discriminator="mode_name")
]

class AdditionalProperty(BaseModel):
    key: str
    value: str

class StopType(StrEnum):
    NAPTAN_ONSTREET_BUS_COACH_STOP_PAIR = "NaptanOnstreetBusCoachStopPair"
    NAPTAN_PUBLIC_BUS_COACH_TRAM = "NaptanPublicBusCoachTram"
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
        StopType.NAPTAN_METRO_PLATFORM
    ] = Field(alias="stopType")

class SingleStopPoint(StopPoint):
    stop_type: Literal[StopType.NAPTAN_PUBLIC_BUS_COACH_TRAM] = Field(alias="stopType")
    stop_letter: str = Field(alias="stopLetter")

class MetroStopPoint(StopPoint):
    stop_type: Literal[StopType.NAPTAN_METRO_STATION] = Field(alias="stopType")

StopPointUnion = Annotated[
    OtherStopPoint | SingleStopPoint | MetroStopPoint,
    Field(discriminator="stop_type")
]

class StopPointResponse(BaseModel):
    stop_points: list[StopPoint] = Field(alias="stopPoints")

class Resource(BaseModel):
    name: str
    resourceId: str

class Entity(BaseModel):
    resources: list[Resource]

class Readings(BaseModel):
    data: list[tuple[int, float]]
