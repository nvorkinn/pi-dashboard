import signal
import sys

import pydantic
import requests

from countdown.display_loop import DisplayLoop
from countdown.config_manager import AppConfig

def main() -> None:
    config = AppConfig()
    loop = DisplayLoop(config)

    # Setup graceful signal handling
    def handle_shutdown(_signum, _frame):
        print("\nShutting down gracefully...")
        # Put your epaper display to sleep to prevent burn-in
        loop.display.shutdown()
        sys.exit(0)
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    loop.run()
