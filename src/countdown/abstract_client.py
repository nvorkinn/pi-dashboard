from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import StrEnum, auto

from countdown.http import build_retrying_session
from display.panel import Panel


class ClientStatus(StrEnum):
    DISABLED = auto()
    UNINITIALISED = auto()
    INITIALISING = auto()
    CONNECTED = auto()
    ERROR = auto()
    FATAL = auto()


class AbstractClient(ABC):
    """Base for the API clients (TflClient, GlowClient, BrokerClient, ...): just a
    shared session and a small per-endpoint cache, available to a client that wants
    to compare a fresh response against the last one it saw (BrokerClient uses this
    for pairing-code change detection). Not force-piped into every client/call --
    see https://github.com/nvorkinn/countdown/issues/54 for the larger plan to use
    this more broadly for change-detection (skip a repaint / e-paper refresh when
    nothing changed)."""

    poll_interval: timedelta = timedelta(minutes=1)

    def __init__(self):
        self.session = build_retrying_session()
        self.cache: dict[str, object] = {}
        self.status: ClientStatus = ClientStatus.UNINITIALISED
        self.last_updated: datetime | None = None

    @abstractmethod
    async def initialise(self) -> None:
        pass

    def is_disabled(self) -> bool:
        return self.status == ClientStatus.DISABLED

    @property
    def is_due(self) -> bool:
        if self.last_updated is None:
            return True
        return datetime.now() - self.last_updated >= self.poll_interval

    async def update(self) -> Panel | None:
        panel = await self._update()
        self.last_updated = datetime.now()
        return panel

    @abstractmethod
    async def _update(self) -> Panel | None:
        pass

    def _cache_and_compare(self, endpoint: str, data: object) -> bool:
        """Returns True if the last call to the same endpoint returned the same data.
        Always False the first time an endpoint is seen -- there's nothing to compare
        against yet, not "unchanged" -- even if that first value happens to be None
        (checked via membership, not `is None`, so a legitimately-None value doesn't
        get mistaken for "never cached" on every subsequent call)."""
        is_first_time = endpoint not in self.cache
        cached = self.cache.get(endpoint)
        self.cache[endpoint] = data
        if is_first_time:
            return False
        return cached == data
