from abc import ABC
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ApiConfig(ABC, BaseModel):
    enabled: bool | None = Field(default=True)


class TflConfig(ApiConfig):
    app_key: str = Field(default="")
    # Flat ordered list of NaPTAN stop IDs to cycle through on the display
    stop_ids: list[str] = Field(default_factory=list)


class SpotifyConfig(ApiConfig):
    # Client credentials/OAuth live entirely in auth-broker now; this device only
    # ever sees whether the panel should be shown, fetched from the broker each
    # cycle (see DisplayLoop.refresh_broker_config).
    enabled: bool | None = Field(default=False)


class WeatherConfig(ApiConfig):
    api_key: str = Field(default="")
    location: str = Field(default="")


class GlowmarktConfig(ApiConfig):
    # None, not "" -- these come from the broker as null when a device's owner
    # hasn't set up Glowmarkt (the common case), and an explicit "not configured"
    # is worth keeping honest rather than folding into the same empty-string
    # convention used elsewhere, since a credential has no legitimate empty value
    # the way e.g. a search query might.
    username: str | None = Field(default=None)
    password: str | None = Field(default=None)

    @field_validator("username", "password", mode="before")
    @classmethod
    def blank_is_not_set(cls, value: Any) -> Any:
        """A cleared field can arrive as "" or whitespace rather than null. Either way
        there's no credential, so it's None: GlowClient then stays disabled and the layout
        leaves the energy panel out, instead of trying to log in with a blank username.
        (The broker leaves `enabled` true when the credentials are cleared.)"""
        if isinstance(value, str) and not value.strip():
            return None
        return value


class NoticeBoardConfig(ApiConfig):
    # Where the weather warnings, floods and road incidents are looked up for. None
    # until the owner sets one; those sources stay quiet until then.
    postcode: str | None = Field(default=None)
    # Not sent by the broker: a copy of AppConfig.tfl, for the stops whose lines and
    # stations the TfL disruptions are about (see AppConfig.share_tfl_with_notice_board).
    tfl: TflConfig = Field(default_factory=TflConfig)


class AppConfig(BaseModel):
    """Everything auth-broker owns: TfL stops, weather location, interval, whether
    Spotify is enabled, and Glowmarkt credentials. A plain BaseModel, not
    BaseSettings -- structurally cannot read .env or any env var.

    Deliberately has no defaults at this level: an AppConfig only ever comes from a
    validated broker response, so one that says "no stops" means the broker said so, not
    that we never heard from it. A response with a section missing is rejected -- and the
    device keeps the config it already had (see DisplayLoop.refresh_broker_config) --
    rather than quietly turning into an empty one that blanks the screen. At boot the app
    waits for a valid config (app.wait_for_config); there is no empty fallback. (Settings
    nested inside a section still default where the broker legitimately omits or nulls
    them.) Tests build one with tests/config_factory.make_config()."""

    interval: int = Field(gt=0, description="The interval in seconds between updates.")
    tfl: TflConfig
    spotify: SpotifyConfig
    weather: WeatherConfig
    glowmarkt: GlowmarktConfig
    notice_board: NoticeBoardConfig = Field(default_factory=NoticeBoardConfig)
    # Required but nullable: the broker sends null once the device is paired.
    pairing_code: str | None
    # What the device still needs before it's worth showing; empty once it's set up.
    setup_missing: list[str]

    @model_validator(mode="before")
    @classmethod
    def share_tfl_with_notice_board(cls, data: Any) -> Any:
        """The notice board's TfL disruptions are for the same stops as the arrivals, so
        it gets its own copy of the tfl section rather than the broker sending it twice.
        Its postcode still comes from the broker's (optional) notice_board section."""
        if isinstance(data, dict) and "tfl" in data:
            notice_board = data.get("notice_board") or {}
            if isinstance(notice_board, NoticeBoardConfig):
                notice_board = notice_board.model_dump()
            data = data | {"notice_board": notice_board | {"tfl": data["tfl"]}}
        return data
