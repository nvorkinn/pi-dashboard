import asyncio
from enum import Enum

from countdown.abstract_client import AbstractClient
from countdown.config_manager import ApiConfig, AppConfig
from countdown.glow_client import GlowClient
from countdown.spotify_client import SpotifyClient
from countdown.tfl_client import TflClient
from countdown.weather_client import WeatherClient
from display.panel import Panel


class ClientClasses(Enum):
    GLOWMARKT = ("glowmarkt", GlowClient)
    TFL = ("tfl", TflClient)
    WEATHER = ("weather", WeatherClient)
    SPOTIFY = ("spotify", SpotifyClient)

    @property
    def api_name(self) -> str:
        return self.value[0]


class ApiRegistry:
    def __init__(self):
        self.clients: dict[str, AbstractClient] = {}
        self.panels: dict[str, Panel | None] = {}

    def build_from_config(self, config: AppConfig):
        for member in ClientClasses:
            name, clazz = member.value
            client_config: ApiConfig = getattr(config, name)
            if client_config.enabled:
                self.clients[name] = clazz(client_config)

    async def authenticate_all(self):
        coros = [client.initialise() for client in self.clients.values()]
        outcomes = await asyncio.gather(*coros, return_exceptions=True)
        # TODO: Do something if Exception

    async def update_all(self) -> dict[str, Panel | None]:
        """Polls whichever clients are due and returns the panels for *all* clients:
        one that isn't due yet keeps its last panel (a Glowmarkt client polling every
        15 minutes must not blank the energy panel on the cycles in between), and one
        that raised keeps its last good panel too -- stale-but-valid beats nothing.
        A client returning None is different: that means "nothing to show" (nothing
        playing, no location configured) and does replace the previous panel."""
        due = [(api_name, client.update()) for api_name, client in self.clients.items() if client.is_due]
        outcomes = await asyncio.gather(*[coro for _, coro in due], return_exceptions=True)

        for (api_name, _), outcome in zip(due, outcomes, strict=True):
            if isinstance(outcome, Exception):
                print(f"Error updating {api_name}: {outcome}")
            else:
                self.panels[api_name] = outcome
        return dict(self.panels)

    def on_config_update(self, new_config: AppConfig) -> None:
        for member in ClientClasses:
            name, clazz = member.value
            current_config = self.clients[name]