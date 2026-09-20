import asyncio
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

# How long to wait between attempts to get a config at boot: the first retry comes after
# INITIAL_RETRY_S, doubling up to MAX_RETRY_S, so a device whose Wi-Fi is still coming up
# tries again quickly, and one whose broker is down for hours isn't hammering it.
INITIAL_RETRY_S = 30
MAX_RETRY_S = 300


def main() -> None:
    """The `countdown` console script's entry point (pyproject.toml). It has to be a plain
    function: the generated wrapper just calls it, so an `async def` here would build a
    coroutine, never run it, and exit 1 -- a crash loop under systemd."""
    asyncio.run(run())


async def wait_for_config(
    broker: BrokerClient,
    display: DisplayController,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_retry: Callable[[], Awaitable[None]] | None = None,
) -> tuple[AppConfig, PairingCodePanel]:
    """Blocks until the broker has given this device a valid config, and returns it (with the
    pairing status that came with it). Everything the app does depends on that config, so
    there's no empty fallback: until it arrives a splash says so (painted
    once -- not on every retry, it's a full refresh) and the attempts continue with backoff.
    Covers a first-time registration failing too, which used to crash-loop the service.
    "Can't reach the broker" and "it answered with something that isn't a valid config" are
    treated alike: either way there's no usable config yet."""
    delay = INITIAL_RETRY_S
    splash_shown = False
    while True:
        try:
            if broker.status != ClientStatus.CONNECTED:
                await broker.initialise()
            return await asyncio.to_thread(broker.fetch_app_config)
        except (requests.exceptions.RequestException, ValueError, KeyError) as e:
            reason = f"{type(e).__name__}: {e}".splitlines()[0]
            print(f"Can't get a valid config from the broker yet ({reason}) -- retrying in {delay}s")
            if not splash_shown:
                display.display_splash(SplashPanel())
                splash_shown = True
            if on_retry:
                await on_retry()
            await sleep(delay)
            delay = min(delay * 2, MAX_RETRY_S)


async def run() -> None:
    # The only thing that can't come from the broker -- it's how this device finds
    # the broker in the first place. Set via the systemd unit's Environment= line
    # (see packaging/systemd/countdown.service). No default: if it's missing, the
    # app should crash loudly rather than silently talk to some baked-in URL.
    broker_url = os.environ["BROKER_URL"]

    # The display exists before the config does, so there's somewhere to show the splash.
    display = DisplayController()

    # Set up before the (possibly long) wait for a config, so a stop request works then too.
    def handle_shutdown(_signum, _frame):
        print("\nShutting down gracefully...")
        # Put your epaper display to sleep to prevent burn-in
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
