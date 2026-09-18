import os
import signal
import sys

import pydantic
import requests

from countdown.broker_client import BrokerClient
from countdown.display_loop import DisplayLoop, fetch_app_config

def main() -> None:
    # The only thing that can't come from the broker -- it's how this device finds
    # the broker in the first place. Set via the systemd unit's Environment= line
    # (see packaging/systemd/countdown.service). No default: if it's missing, the
    # app should crash loudly rather than silently talk to some baked-in URL.
    broker_url = os.environ["BROKER_URL"]
    broker = BrokerClient(broker_url)
    config, pairing_code_panel = fetch_app_config(broker)
    loop = DisplayLoop(broker, config, pairing_code_panel)

    # Setup graceful signal handling
    def handle_shutdown(_signum, _frame):
        print("\nShutting down gracefully...")
        # Put your epaper display to sleep to prevent burn-in
        loop.display.shutdown()
        sys.exit(0)
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    loop.run()
