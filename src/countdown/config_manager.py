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
    """The only settings actually read from .env/real env vars -- genuinely local
    values the broker never knows about and could never provide: where to find it,
    and this device's own Glowmarkt energy account."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    broker_url: str = Field(default="https://auth.nikolaivorkinn.com", description="Base URL of the auth-broker service.")
    glowmarkt: GlowmarktConfig = Field(default_factory=GlowmarktConfig)


class LiveConfig(BaseModel):
    """Everything auth-broker owns: TfL stops, weather location, interval, whether
    Spotify is enabled. Deliberately NOT a BaseSettings/not read from .env or any
    env var, and never persisted anywhere -- a local copy of these would just be a
    stale, un-synced guess sitting next to the real thing. Starts empty/off and is
    only ever populated by a successful DisplayLoop.refresh_broker_config() fetch;
    if the broker is unreachable, these fields simply stay whatever they last were
    (empty on a fresh boot) rather than falling back to something written down
    once and never touched again."""

    interval: int = Field(default=15, gt=0, description="The interval in seconds between updates.")
    tfl: TflConfig = Field(default_factory=TflConfig)
    spotify: SpotifyConfig = Field(default_factory=SpotifyConfig)
    weather: WeatherConfig = Field(default_factory=WeatherConfig)
