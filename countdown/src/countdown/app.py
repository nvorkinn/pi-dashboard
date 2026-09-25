import asyncio
import logging
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import requests

from countdown.abstract_client import ClientStatus
from countdown.api_registry import ApiRegistry
from countdown.broker_client import BrokerClient
from countdown.config_manager import AppConfig
from countdown.device_status import DeviceStatus
from countdown.display_loop import DisplayLoop
from display.display import DisplayController
from display.pairing_code_panel import PairingCodePanel
from display.splash_panel import SplashPanel

logger = logging.getLogger(__name__)

# Backoff between attempts to get a config at boot: doubles from INITIAL_RETRY_S up to MAX_RETRY_S.
INITIAL_RETRY_S = 30
MAX_RETRY_S = 300


def main() -> None:
    """The `countdown` console script's entry point. Must stay sync: the generated wrapper
    never awaits, so an `async def` here would exit 1 without running anything."""
    configure_logging()
    asyncio.run(run())


def configure_logging() -> None:
    """No timestamp: journald adds its own. An unrecognised LOG_LEVEL falls back to INFO."""
    level = logging.getLevelNamesMapping().get(os.environ.get("LOG_LEVEL", "").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s %(filename)s:%(lineno)d %(message)s",
    )


async def wait_for_config(
    broker: BrokerClient,
    display: DisplayController,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_retry: Callable[[], Awaitable[None]] | None = None,
) -> tuple[AppConfig, PairingCodePanel]:
    """Blocks until the broker returns a valid config, retrying with backoff. The splash is
    painted once, not on every retry, since it's a full refresh."""
    delay = INITIAL_RETRY_S
    splash_shown = False
    while True:
        try:
            if broker.status != ClientStatus.CONNECTED:
                await broker.initialise()
            return await asyncio.to_thread(broker.fetch_app_config)
        except (requests.exceptions.RequestException, ValueError, KeyError) as e:
            reason = f"{type(e).__name__}: {e}".splitlines()[0]
            logger.warning(f"Can't get a valid config from the broker yet ({reason}) -- retrying in {delay}s")
            if not splash_shown:
                display.display_splash(SplashPanel())
                splash_shown = True
            if on_retry:
                await on_retry()
            await sleep(delay)
            delay = min(delay * 2, MAX_RETRY_S)


async def run() -> None:
    # No default: crash loudly rather than silently talk to some baked-in URL.
    broker_url = os.environ["BROKER_URL"]

    # The display exists before the config does, so there's somewhere to show the splash.
    display = DisplayController()

    # Set up before the (possibly long) wait for a config, so a stop request works then too.
    def handle_shutdown(_signum, _frame):
        logger.info("Shutting down gracefully...")
        # Sleep the e-paper to prevent burn-in.
        display.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Created before the config exists, so the wait for it can be reported to Home Assistant too.
    status = DeviceStatus(display=display)
    registry = ApiRegistry(status)

    broker = BrokerClient(broker_url)
    config, pairing_code_panel = await wait_for_config(broker, display, on_retry=registry.publish_health)
    status.last_broker_sync = datetime.now(UTC)
    await DisplayLoop(broker, config, pairing_code_panel, display, registry).run()
