from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TflConfig(BaseModel):
    app_key: str = Field(default="")
    # Flat ordered list of NaPTAN stop IDs to cycle through on the display
    stop_ids: list[str] = Field(default_factory=list)


class SpotifyConfig(BaseModel):
    # Client credentials/OAuth live entirely in auth-broker now; this device only
    # ever sees whether the panel should be shown, fetched from the broker each
    # cycle (see DisplayLoop.refresh_broker_config).
    enabled: bool = Field(default=False)


class WeatherConfig(BaseModel):
    api_key: str = Field(default="")
    location: str = Field(default="")


class GlowmarktConfig(BaseModel):
    username: str = Field(default="")
    password: str = Field(default="")


class AppConfig(BaseSettings):
    """Local bootstrap defaults, read from .env/real env vars only -- there's no
    config.json/local editing UI any more, since auth-broker is now authoritative
    for tfl.stop_ids, weather.location, spotify.enabled and interval (see
    DisplayLoop.refresh_broker_config). These fields only matter for the very
    first display cycle, before the first broker sync completes."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    tfl: TflConfig = Field(default_factory=TflConfig)
    interval: int = Field(default=15, gt=0, description="The interval in seconds between updates.")
    broker_url: str = Field(default="https://auth.nikolaivorkinn.com", description="Base URL of the auth-broker service.")
    spotify: SpotifyConfig = Field(default_factory=SpotifyConfig)
    weather: WeatherConfig = Field(default_factory=WeatherConfig)
    glowmarkt: GlowmarktConfig = Field(default_factory=GlowmarktConfig)
