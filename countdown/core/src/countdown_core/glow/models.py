from pydantic import BaseModel


class Resource(BaseModel):
    name: str
    resourceId: str


class Entity(BaseModel):
    resources: list[Resource]


class Readings(BaseModel):
    data: list[tuple[int, float]]
