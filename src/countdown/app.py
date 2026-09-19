import asyncio
import os
import signal
import sys

from countdown.broker_client import BrokerClient
from countdown.display_loop import DisplayLoop


def main() -> None:
    """The `countdown` console script's entry point (pyproject.toml). It has to be a plain
    function: the generated wrapper just calls it, so an `async def` here would build a
    coroutine, never run it, and exit 1 -- a crash loop under systemd."""
    asyncio.run(run())


async def run() -> None:
    # The only thing that can't come from the broker -- it's how this device finds
    # the broker in the first place. Set via the systemd unit's Environment= line
    # (see packaging/systemd/countdown.service). No default: if it's missing, the
    # app should crash loudly rather than silently talk to some baked-in URL.
    broker_url = os.environ["BROKER_URL"]
    broker = BrokerClient(broker_url)
    await broker.initialise()
    config, pairing_code_panel = broker.fetch_app_config()
    loop = DisplayLoop(broker, config, pairing_code_panel)

    # Setup graceful signal handling
    def handle_shutdown(_signum, _frame):
        print("\nShutting down gracefully...")
        # Put your epaper display to sleep to prevent burn-in
        loop.display.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    await loop.run()
