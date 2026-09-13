import signal
import sys
import threading
import time

import pydantic
import requests

from countdown.glow_client import GlowClient
from countdown.tfl_client import TflClient
from countdown.spotify_client import SpotifyClient
from countdown.flask import app
from countdown.config_manager import config_manager
from countdown.weather_client import WeatherClient
from display.combined_arrival_panel import CombinedArrivalPanel
from display.display import DisplayController
from display.energy_panel import EnergyPanel

def safe_fetch(func, fallback):
    try:
        return func()
    except requests.exceptions.RequestException as e:
        print(f"Exception with API call to Glowmarkt: {e}")
        return fallback
    except pydantic.ValidationError as e:
        print(f"Pydantic validation error: {e}")
        return fallback


def _reload_tfl_client_if_changed(tfl: TflClient, config_manager) -> TflClient:
    """Reload the TfL client if config.json changed on disk. Building a new TflClient
    can hit the network (resolving a postcode to nearby stops), so a failure here must
    not take down the whole display loop -- keep serving with the old client instead."""
    if not config_manager.has_changed():
        return tfl
    try:
        new_config = config_manager.load_config()
        return TflClient(new_config)
    except (requests.exceptions.RequestException, pydantic.ValidationError) as e:
        print(f"Failed to reload TfL client after config change, keeping old one: {e}")
        return tfl

def main() -> None:
    config = config_manager.load_config()
    flask_thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=config.config_port),
        daemon=True
    )
    flask_thread.start()
    display = DisplayController()
    # Setup graceful signal handling
    def handle_shutdown(_signum, _frame):
        print("\nShutting down gracefully...")
        # Put your epaper display to sleep to prevent burn-in
        display.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    tfl = TflClient(config)
    glow = GlowClient(config)
    spotify = SpotifyClient(config.spotify)
    weather = WeatherClient(config.weather)
    resource_id = glow.get_electricity_resource_id()
    energy = {
        "day": None,
        "month": None,
        "year": None
    }
    energy_panel = current_track = weather_panel = None
    page_count = tfl.get_page_count()
    page = 0
    while True:
        try:
            arrival_panel = CombinedArrivalPanel(tfl.get_next_departures())
            if page % page_count == 0:
                energy["day"] = safe_fetch(lambda: glow.get_day_readings(resource_id), energy["day"])
                energy["month"] = safe_fetch(lambda: glow.get_month_readings(resource_id), energy["month"])
                energy["year"] = safe_fetch(lambda: glow.get_year_readings(resource_id), energy["year"])
                energy_panel = EnergyPanel(energy["day"], energy["month"], energy["year"])
                current_track = spotify.get_current_track()
                weather_panel = safe_fetch(lambda: weather.get_weather(), weather_panel)
                display.display_screen(arrival_panel, energy_panel, current_track, weather_panel)
            else:
                display.display_partial(arrival_panel, energy_panel, current_track, weather_panel)
        except requests.exceptions.RequestException as e:
            print(f"Network error encountered: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

        time.sleep(config.interval)

        tfl = _reload_tfl_client_if_changed(tfl, config_manager)

        page += 1
        if page == page_count:
            page = 0
