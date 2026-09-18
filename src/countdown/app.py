import os
import signal
import sys

import pydantic
import requests

from countdown.display_loop import DisplayLoop

def main() -> None:
    # The only thing that can't come from the broker -- it's how this device finds
    # the broker in the first place. Set via the systemd unit's Environment= line
    # (see packaging/systemd/countdown.service). No default: if it's missing, the
    # app should crash loudly rather than silently talk to some baked-in URL.
    broker_url = os.environ["BROKER_URL"]
    loop = DisplayLoop(broker_url)

    # Setup graceful signal handling
    def handle_shutdown(_signum, _frame):
        print("\nShutting down gracefully...")
        # Put your epaper display to sleep to prevent burn-in
        loop.display.shutdown()
        sys.exit(0)
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    loop.run()
