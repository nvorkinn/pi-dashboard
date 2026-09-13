import signal
import sys
import threading
import time
import requests

from countdown.glow_client import GlowClient
from countdown.tfl_client import TflClient
from countdown.spotify_client import SpotifyClient
from countdown.flask import app
from countdown.config_manager import config_manager
from display.combined_arrival_panel import CombinedArrivalPanel
from display.display import DisplayController
from display.energy_panel import EnergyPanel

def safe_fetch(func, fallback):
    try:
        return func()
    except Exception:
        return fallback

def main() -> None:


    config = config_manager.load_config()
    sleep_interval = get_sleep_interval(config)
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=config.get("config_port")),
        daemon=True
    )
    flask_thread.start()
    display = DisplayController()
    # Setup graceful signal handling
    def handle_shutdown(signum, frame):
        print("\nShutting down gracefully...")
        # Put your ePaper display to sleep to prevent burn-in
        # epd.sleep()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    tfl = TflClient(config)
    glow = GlowClient(config)
    spotify = SpotifyClient(config["spotify"])
    resource_id = glow.get_electricity_resource_id()
    energy = {
        "day": None,
        "month": None,
        "year": None
    }
    while True:
        try:
            arrival_panel = CombinedArrivalPanel(tfl.get_next_departures())
            energy["day"] = safe_fetch(lambda: glow.get_day_readings(resource_id), energy["day"])
            energy["month"] = safe_fetch(lambda: glow.get_month_readings(resource_id), energy["month"])
            energy["year"] = safe_fetch(lambda: glow.get_year_readings(resource_id), energy["year"])
            energy_panel = EnergyPanel(energy["day"], energy["month"], energy["year"])
            current_track = spotify.get_current_track()
            display.display_screen(arrival_panel, energy_panel, current_track)
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
