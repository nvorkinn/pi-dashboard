from datetime import timedelta
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, HttpUrl

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


class TopResponse[T: (Track, Artist)](BaseModel):
    items: list[T]
