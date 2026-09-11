from enum import StrEnum, IntEnum

from pydantic import BaseModel, Field

class Mode(StrEnum):
    BUS = "bus"
    TUBE = "tube"

class Mode2(IntEnum):
    ONE = 1
    TWO = 2

class Arrival(BaseModel):
    stop: str | None = None
    station: str = Field(alias="stationName")
    line: str = Field(alias="lineName")
    destination: str = Field(alias="destinationName")
    towards: str
    time_to_station: int = Field(alias="timeToStation")
    mode: Mode = Field(alias="modeName")
    platform: str = Field(alias="platformName")

class AdditionalProperty(BaseModel):
    key: str
    value: str

class StopPoint(BaseModel):
    naptan_id: str = Field(alias="naptanId")
    additional_properties: list[AdditionalProperty] = Field(alias="additionalProperties")

class StopPointResponse(BaseModel):
    stop_points: list[StopPoint] = Field(alias="stopPoints")

class Resource(BaseModel):
    name: str
    resourceId: str

class Entity(BaseModel):
    resources: list[Resource]

class Readings(BaseModel):
    data: list[tuple[int, float]]
