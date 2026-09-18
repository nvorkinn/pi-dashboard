from pydantic import BaseModel, Field


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
    # None, not "" -- these come from the broker as null when a device's owner
    # hasn't set up Glowmarkt (the common case), and an explicit "not configured"
    # is worth keeping honest rather than folding into the same empty-string
    # convention used elsewhere, since a credential has no legitimate empty value
    # the way e.g. a search query might.
    username: str | None = Field(default=None)
    password: str | None = Field(default=None)


class AppConfig(BaseModel):
    """Everything auth-broker owns: TfL stops, weather location, interval, whether
    Spotify is enabled, and Glowmarkt credentials. A plain BaseModel, not
    BaseSettings -- structurally cannot read .env or any env var, and is never
    persisted anywhere, so there's no local copy of any of this to go stale. Starts
    empty/off and is only ever populated by a successful
    DisplayLoop.refresh_broker_config() fetch; if the broker is unreachable, these
    fields simply stay whatever they last were (empty on a fresh boot) rather than
    falling back to something written down once and never touched again."""

    interval: int = Field(default=15, gt=0, description="The interval in seconds between updates.")
    tfl: TflConfig = Field(default_factory=TflConfig)
    spotify: SpotifyConfig = Field(default_factory=SpotifyConfig)
    weather: WeatherConfig = Field(default_factory=WeatherConfig)
    glowmarkt: GlowmarktConfig = Field(default_factory=GlowmarktConfig)
