import threading
import time
import requests
from countdown.tfl_client import TflClient
from countdown.flask import app
from countdown.config_manager import config_manager

def main() -> None:
    config = config_manager.load_config()
    sleep_interval = get_sleep_interval(config)
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=config.get("config_port")),
        daemon=True
    )
    flask_thread.start()
    tfl = TflClient(config)
    last = []
    while True:
        try:
            next_departures = tfl.get_next_departures()
            if next_departures != last:
                update_screen(next_departures)
                last = next_departures
        except requests.exceptions.RequestException as e:
            print(f"Network error encountered: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

        time.sleep(sleep_interval)

        if config_manager.has_changed():
            new_config = config_manager.load_config()
            tfl = TflClient(new_config)

def get_sleep_interval(config: dict[str, object]) -> int | float:
    interval = config['interval']
    if not isinstance(interval, (int, float)) or isinstance(interval, bool):
        raise TypeError(
            f"Invalid sleep interval type: {type(interval).__name__}. "
            "Must be an int or a float."
        )
    elif interval <= 0:
        raise ValueError(f"Sleep interval cannot be negative: {interval}")
    else:
        return interval

def update_screen(arrivals: list) -> None:
    return
