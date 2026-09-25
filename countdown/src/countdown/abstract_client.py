import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from enum import StrEnum, auto

from countdown.config_manager import ApiConfig
from countdown.http import build_retrying_session
from display.message_panel import MessagePanel
from display.panel import Panel

logger = logging.getLogger(__name__)

# A client call slower than this is logged, so a slow API shows up in the journal by name
# instead of just making the whole cycle late.
SLOW_CALL_S = 5


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
    see https://github.com/nvorkinn/pi-dashboard/issues/8 for the larger plan to use
    this more broadly for change-detection (skip a repaint / e-paper refresh when
    nothing changed).

    _initialise() and _update() are plain, blocking functions (every client talks to
    its API with `requests`). initialise() and update() run them in a worker thread, so
    the ApiRegistry's asyncio.gather() over several clients really does poll them
    concurrently -- a cycle takes as long as the slowest API, not all of them added up --
    and a slow API can't freeze the event loop. That means a hook must not touch
    anything that's only safe on the main thread: build the panel's data there and let
    the display render it (Pillow, SPI) later."""

    poll_interval: timedelta = timedelta(minutes=1)
    # Whose area a MessagePanel standing in for this client's panel belongs to.
    panel_title: str = ""
    panel_logo: str | None = None

    def __init__(self, config: ApiConfig | None = None):
        self.config = config
        self.session = build_retrying_session()
        self.cache: dict[str, object] = {}
        self.status: ClientStatus = ClientStatus.UNINITIALISED
        self.last_updated: datetime | None = None

    def __del__(self):
        self.session.close()

    async def initialise(self) -> None:
        """Runs the client's own _initialise() (authenticating, resolving ids, ...)
        and tracks the outcome in self.status: CONNECTED on success, ERROR -- and the
        exception re-raised for the caller to log -- on failure. update() calls this
        itself for a client that never got, or failed, its initialisation, so a
        boot-time failure (API down, no network yet) heals on its own instead of
        leaving the client broken until its config happens to change. A disabled
        client stays disabled and makes no calls."""
        if self.is_disabled():
            return
        self.status = ClientStatus.INITIALISING
        started = time.monotonic()
        try:
            await asyncio.to_thread(self._initialise)
        except Exception:
            self.status = ClientStatus.ERROR
            raise
        finally:
            self._log_if_slow("initialise", started)
        self.status = ClientStatus.CONNECTED

    @abstractmethod
    def _initialise(self) -> None:
        pass

    def _log_if_slow(self, what: str, started: float) -> None:
        elapsed = time.monotonic() - started
        if elapsed >= SLOW_CALL_S:
            logger.warning(f"{type(self).__name__}: {what} took {elapsed:.1f}s")

    def needs_refresh(self, new_config: ApiConfig) -> bool:
        """Whether `new_config` differs from the one this client was built with in a way
        that means it should be rebuilt and re-initialised (ApiRegistry does that).
        Defaults to "any change at all"; a client overrides this when some of its
        config doesn't affect it (see WeatherClient), so an irrelevant change doesn't
        throw away its state -- Glowmarkt's token and reading cache, TfL's resolved
        stops -- for nothing."""
        return self.config != new_config

    def is_disabled(self) -> bool:
        return self.status == ClientStatus.DISABLED

    @property
    def is_due(self) -> bool:
        if self.last_updated is None:
            return True
        return datetime.now() - self.last_updated >= self.poll_interval

    async def update(self) -> Panel | None:
        """Polls the API and returns its panel. A client that isn't CONNECTED yet
        (UNINITIALISED, or ERROR from a failed attempt) initialises first; if that
        fails again the exception propagates, and last_updated is still stamped so the
        retry waits a full poll_interval rather than hammering an API that's down or
        rejecting credentials (Glowmarkt rate-limits those) every cycle."""
        if self.is_disabled():
            panel = None
        else:
            if self.status in (ClientStatus.UNINITIALISED, ClientStatus.ERROR):
                try:
                    await self.initialise()
                except Exception:
                    self.last_updated = datetime.now()
                    raise
            started = time.monotonic()
            try:
                panel = await asyncio.to_thread(self._update)
            finally:
                self._log_if_slow("update", started)
        self.last_updated = datetime.now()
        return panel

    @abstractmethod
    def _update(self) -> Panel | None:
        pass

    @classmethod
    def message_panel(cls, message: str) -> MessagePanel:
        return MessagePanel(cls.panel_title, message, cls.panel_logo)

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
