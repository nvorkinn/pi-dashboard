import signal
import sys
import threading

import pydantic
import requests

from countdown.display_loop import DisplayLoop
from countdown.flask import app
from countdown.config_manager import config_manager

def main() -> None:
    config = config_manager.load_config()
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=config.config_port),
        daemon=True
    )
    flask_thread.start()
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

