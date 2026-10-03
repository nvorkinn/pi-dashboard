import asyncio
import logging
from datetime import timedelta
from enum import Enum

from countdown_core.config_server.models import ApiConfig, AppConfig
from countdown_core.core.abstract_client import AbstractClient, ClientStatus
from countdown_core.core.panel import Panel
from countdown_core.glow.glow_client import GlowClient
from countdown_core.home_assistant.device_status import DeviceStatus
from countdown_core.home_assistant.mqtt_publisher import MqttPublisher
from countdown_core.notices.notice_board_client import NoticeBoardClient
from countdown_core.spotify.spotify_client import SpotifyClient
from countdown_core.tfl.tfl_client import TflClient
from countdown_core.weather.weather_client import WeatherClient

logger = logging.getLogger(__name__)


class ClientClasses(Enum):
    NOTICE_BOARD = ("notice_board", NoticeBoardClient)
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

    def _update(self) -> Panel:
        raise self.error


class ApiRegistry:
    def __init__(self, status: DeviceStatus | None = None):
        self.clients: dict[str, AbstractClient] = {}
        self.panels: dict[str, Panel | None] = {}  # None only from a DISABLED client
        self.status = status or DeviceStatus()
        # Shares self.clients (mutated in place, never reassigned) to read their statuses.
        self.pub = MqttPublisher.from_env(self.clients, [member.api_name for member in ClientClasses], self.status)

    async def on_config_update(self, config: AppConfig) -> None:
        """Brings the clients in line with `config`, rebuilding only those whose
        needs_refresh() says so. Failures are logged, not raised, so one broken API
        doesn't take the others down."""
        to_initialise: dict[str, AbstractClient] = {}
        for member in ClientClasses:
            name, clazz = member.value
            client_config: ApiConfig = getattr(config, name)
            current = self.clients.get(name)

            if not client_config.enabled:
                # No client at all, so one switched back on later is built fresh.
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

    async def update_all(self) -> dict[str, Panel]:
        """Polls the clients that are due and returns a panel for every API. A client that
        isn't due, or that raised, keeps its last panel."""
        due = [(api_name, client.update()) for api_name, client in self.clients.items() if client.is_due]
        outcomes = await asyncio.gather(*[coro for _, coro in due], return_exceptions=True)

        for (api_name, _), outcome in zip(due, outcomes, strict=True):
            if isinstance(outcome, Exception):
                logger.error(f"Error updating {api_name}: {outcome}", exc_info=outcome)
            else:
                self.panels[api_name] = outcome
        return {member.api_name: self._panel_for(member) for member in ClientClasses}

    def available(self) -> frozenset[ClientClasses]:
        """The APIs that get an area on the screen. A failing client still counts, so its
        area says "Could not connect" rather than vanishing."""
        return frozenset(
            member
            for member in ClientClasses
            if (client := self.clients.get(member.api_name)) is not None and not client.is_disabled()
        )

    def show_stops(self, count: int) -> None:
        """Tells the TfL client how many stops the layout has room for. Call after every
        on_config_update(), since that may have rebuilt the client."""
        tfl = self.clients.get(ClientClasses.TFL.api_name)
        if isinstance(tfl, TflClient):
            tfl.stops_per_update = count

    def _panel_for(self, member: ClientClasses) -> Panel:
        """The API's last panel, or a MessagePanel saying why there isn't one."""
        name, clazz = member.value
        client = self.clients.get(name)
        if client is None or client.is_disabled():
            return clazz.message_panel("Not configured")
        return self.panels.get(name) or clazz.message_panel("Could not connect")

    async def publish_health(self, force: bool = False) -> None:
        """Logged, never raised: telemetry must not cost the display a refresh. `force`
        skips the once-a-minute limit (for a stage change)."""
        if not force and not self.pub.is_due:
            return
        try:
            await self.pub.update()
        except Exception as e:
            logger.exception(f"Error publishing health over MQTT: {e}")
