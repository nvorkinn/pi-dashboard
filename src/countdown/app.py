import threading
import time
import requests
import sys
sys.path.insert(1, "./lib")

import epd7in5_V2

from countdown.glow_client import GlowClient
from countdown.tfl_client import TflClient
from countdown.spotify_client import SpotifyClient
from countdown.flask import app
from countdown.config_manager import config_manager
from display.display import display_screen


def main() -> None:
    config = config_manager.load_config()
    sleep_interval = get_sleep_interval(config)
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=config.get("config_port")),
        daemon=True
    )
    epd = epd7in5_V2.EPD()
    epd.init()
    epd.Clear()
    flask_thread.start()
    tfl = TflClient(config)
    glow = GlowClient(config)
    spotify = SpotifyClient(config["spotify"])
    resource_id = glow.get_electricity_resource_id()
    show_bus = False
    while True:
        try:
            next_departures = tfl.get_next_departures(show_bus := not show_bus)
            readings = (
                glow.get_day_readings(resource_id),
                glow.get_month_readings(resource_id),
                glow.get_year_readings(resource_id)
            )
            current_track = spotify.get_current_track()
            display_screen(epd, next_departures, readings, current_track)
        except requests.exceptions.RequestException as e:
            print(f"Network error encountered: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

        epd.sleep()
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
