import asyncio
import logging
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import requests

from countdown_core.config_server.broker_client import BrokerClient
from countdown_core.config_server.models import AppConfig
from countdown_core.core.api_registry import ApiRegistry
from countdown_core.core.display import DisplayController
from countdown_core.core.display_loop import DisplayLoop
from countdown_core.core.targets import DisplayTarget
from countdown_core.home_assistant.device_status import DeviceStatus
from countdown_core.system_screens.pairing_code_panel import PairingCodePanel
from countdown_credentials.registration import RendererRegistrar, RendererRegistration

logger = logging.getLogger(__name__)

# Backoff between attempts to get a config at boot: doubles from INITIAL_RETRY_S up to MAX_RETRY_S.
INITIAL_RETRY_S = 30
MAX_RETRY_S = 300


MakeTarget = Callable[[RendererRegistration], DisplayTarget]


def main(make_target: MakeTarget, standalone: bool) -> None:
    """Called by the console scripts (countdown_standalone, countdown_server), each passing the
    `make_target` that knows its screens, and whether the device is its own screen (standalone)
    or renders for a separate one. Must stay sync: the generated wrapper never awaits, so an
    `async def` here would exit 1 without running anything."""
    configure_logging()
    asyncio.run(run(make_target, standalone))


def configure_logging() -> None:
    """No timestamp: journald adds its own. An unrecognised LOG_LEVEL falls back to INFO."""
    level = logging.getLevelNamesMapping().get(os.environ.get("LOG_LEVEL", "").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s %(filename)s:%(lineno)d %(message)s",
    )


async def wait_for_config(
    broker: BrokerClient,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_retry: Callable[[], Awaitable[None]] | None = None,
) -> tuple[AppConfig, PairingCodePanel]:
    """Blocks until the broker returns a valid config, retrying with backoff. `on_retry` is
    awaited before each retry."""
    delay = INITIAL_RETRY_S
    while True:
        try:
            return await asyncio.to_thread(broker.fetch_app_config)
        except (requests.exceptions.RequestException, ValueError, KeyError) as e:
            reason = f"{type(e).__name__}: {e}".splitlines()[0]
            logger.warning(f"Can't get a valid config from the broker yet ({reason}) -- retrying in {delay}s")
            if on_retry:
                await on_retry()
            await sleep(delay)
            delay = min(delay * 2, MAX_RETRY_S)


async def run(make_target: MakeTarget, standalone: bool) -> None:
    # No default: crash loudly rather than silently talk to some baked-in URL.
    registrar = RendererRegistrar(os.environ["BROKER_URL"], standalone=standalone)
    # Nothing happens until the device is registered, standalone or split alike: without it there's
    # no config to render, and nowhere a split renderer's frames could go.
    registration = await registrar.register()

    display = DisplayController(make_target(registration))

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
    registry = ApiRegistry(registration, status)

    broker = BrokerClient(registration)
    config, pairing_code_panel = await wait_for_config(broker, on_retry=registry.publish_health)
    status.last_broker_sync = datetime.now(UTC)
    await DisplayLoop(broker, config, pairing_code_panel, display, registry).run()
