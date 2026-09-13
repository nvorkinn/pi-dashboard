from pathlib import Path
from pydantic import BaseModel, Field, HttpUrl
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

class BusConfig(BaseModel):
    postcode: str = Field(pattern=r"^([Gg][Ii][Rr] 0[Aa]{2})|((([A-Za-z][0-9]{1,2})|(([A-Za-z][A-Za-z][0-9]{1,2})|([A-Za-z][0-9][A-Za-z])|([A-Za-z][A-Za-z][0-9][A-Za-z]))) {0,1}[0-9][A-Za-z]{2})$")
    compass_point: str = Field(pattern=r"^(N|S|E|W)$")
    stop_ids: list[str] = Field(default=[])

class TubeConfig(BaseModel):
    stop_ids: list[str] = Field(default=[])

class SpotifyConfig(BaseModel):
    enabled: bool = Field(default=False)
    client_id: str = Field(default="")
    client_secret: str = Field(default="")
    redirect_uri: HttpUrl

class WeatherConfig(BaseModel):
    api_key: str = Field(default="")
    location: str = Field(default="")

class GlowmarktConfig(BaseModel):
    username: str = Field(default="")
    password: str = Field(default="")

class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        json_file="config.json",
        extra="ignore",
    )

    tfl_api_app_key: str = Field(default="")
    bus: BusConfig = Field(default_factory=BusConfig)
    tube: TubeConfig = Field(default_factory=TubeConfig)
    interval: int = Field(default=15, gt=0, description="The interval in seconds between updates.")
    config_port: int = Field(default=4000, description="The port on which the config server will run.")
    spotify: SpotifyConfig = Field(default_factory=SpotifyConfig)
    weather: WeatherConfig = Field(default_factory=WeatherConfig)
    glowmarkt: GlowmarktConfig = Field(default_factory=GlowmarktConfig)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        sources = [init_settings, dotenv_settings, env_settings]
        config_file = Path("config.json")
        if config_file.exists():
            sources.append(JsonConfigSettingsSource(settings_cls, json_file=config_file))
        return tuple(sources)

class ConfigManager:
    def __init__(self):
        self.config_path = Path("config.json")
        self._last_mtime: float = 0.0

    def has_changed(self) -> bool:
        """Check if the config file has been modified on disk."""
        try:
            current_mtime = self.config_path.stat().st_mtime
            return current_mtime > self._last_mtime
        except OSError:
            return False

    def load_config(self) -> AppConfig:
        if self.config_path.exists():
            self._last_mtime = self.config_path.stat().st_mtime
        return AppConfig()

    def save_config(self, new_config: AppConfig):
        # Dump model while omitting sensitive credentials from being written to config.json
        dump = new_config.model_dump(mode="json", exclude={"glowmarkt"})
        # Remove secrets if they were loaded via env so they don't persist back to config.json
        self.config_path.write_text(new_config.model_dump_json(indent=4, exclude={"glowmarkt"}))

config_manager = ConfigManager()
