import asyncio
import logging
from datetime import timedelta
from enum import Enum

from countdown.abstract_client import AbstractClient, ClientStatus
from countdown.config_manager import ApiConfig, AppConfig
from countdown.device_status import DeviceStatus
from countdown.glow_client import GlowClient
from countdown.mqtt_publisher import MqttPublisher
from countdown.spotify_client import SpotifyClient
from countdown.tfl_client import TflClient
from countdown.weather_client import WeatherClient
from display.panel import Panel

logger = logging.getLogger(__name__)


class ClientClasses(Enum):
    GLOWMARKT = ("glowmarkt", GlowClient)
    TFL = ("tfl", TflClient)
    WEATHER = ("weather", WeatherClient)
    SPOTIFY = ("spotify", SpotifyClient)

    @property
    def api_name(self) -> str:
        return self.value[0]


class FailedClient(AbstractClient):
    """Stands in for a client whose constructor raised, so the failure shows as an error status
    (and in HA) instead of the client silently being missing. Rebuilt when its config changes."""

    poll_interval = timedelta(hours=1)

    def __init__(self, config: ApiConfig, error: Exception):
        super().__init__(config)
        self.error = error
        self.status = ClientStatus.ERROR

    def _initialise(self) -> None:
        raise self.error

    def _update(self) -> Panel | None:
        raise self.error


class ApiRegistry:
    def __init__(self, status: DeviceStatus | None = None):
        self.clients: dict[str, AbstractClient] = {}
        self.panels: dict[str, Panel | None] = {}
        self.status = status or DeviceStatus()
        # Shares self.clients (mutated in place, never reassigned) to read their statuses.
        self.pub = MqttPublisher.from_env(self.clients, [member.api_name for member in ClientClasses], self.status)

    async def on_config_update(self, config: AppConfig) -> None:
        """Brings the registry in line with `config`, touching only what changed: a
        client that's now disabled is dropped (with its panel), a newly enabled one is
        built, and an existing one is asked via needs_refresh() whether the new config
        matters to it -- if so it's replaced by a fresh client, if not it carries on
        with its state intact. Used for the first build too (nothing is registered
        yet, so everything enabled is new). Construction and initialise() failures are
        logged, not raised: one broken API must not take the others down."""
        to_initialise: dict[str, AbstractClient] = {}
        for member in ClientClasses:
            name, clazz = member.value
            client_config: ApiConfig = getattr(config, name)
            current = self.clients.get(name)

            if not client_config.enabled:
                self._drop(name)
            elif current is None or current.needs_refresh(client_config):
                # The old panel came from the old config, so it goes too.
                self._drop(name)
                try:
                    to_initialise[name] = self.clients[name] = clazz(client_config)
                except Exception as e:
                    logger.exception(f"Error building {name} client: {e}")
                    self.clients[name] = FailedClient(client_config, e)

        outcomes = await asyncio.gather(*[c.initialise() for c in to_initialise.values()], return_exceptions=True)
        for name, outcome in zip(to_initialise, outcomes, strict=True):
            if isinstance(outcome, Exception):
                logger.error(f"Error initialising {name}: {outcome}", exc_info=outcome)

    def _drop(self, name: str) -> None:
        self.clients.pop(name, None)
        self.panels.pop(name, None)

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
                logger.error(f"Error updating {api_name}: {outcome}", exc_info=outcome)
            else:
                self.panels[api_name] = outcome
        return dict(self.panels)

    async def publish_health(self, force: bool = False) -> None:
        """Called by the loop every cycle, whatever stage the device is in. Like a client
        failing, an MQTT failure is logged, never raised: telemetry must not cost the display
        a refresh. `force` skips the once-a-minute limit, for a stage change."""
        if not force and not self.pub.is_due:
            return
        try:
            await self.pub.update()
        except Exception as e:
            logger.exception(f"Error publishing health over MQTT: {e}")
