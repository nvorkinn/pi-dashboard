from datetime import datetime
from typing import Any
import sys
sys.path.insert(1, "./lib")

import epd7in5_V2
from PIL import Image, ImageDraw

from countdown.models import Arrival, Mode
from display.spotify_panel import build_spotify_panel
from display.utils import add_border, TOTAL_WIDTH, TOTAL_HEIGHT
from display.bus_panel import create_panel_for_station, build_tfl_panel
from display.energy_panel import build_energy_panel

def display_screen(epd: epd7in5_V2.EPD, departures: list[Any], readings: tuple[list[float], list[float], list[float]], current_track: dict[str, str] | None) -> None:
    img = Image.new("RGBA", (TOTAL_WIDTH, TOTAL_HEIGHT), (255, 255, 255, 255))

    # Departures
    bus_stop_panel = build_tfl_panel(departures)
    img.paste(bus_stop_panel, (5, 5), bus_stop_panel)

    energy_panel = build_energy_panel(readings)
    img.paste(energy_panel, (0, TOTAL_HEIGHT - energy_panel.size[1]))

    draw = ImageDraw.Draw(img)
    if current_track:
        spotify_x = 10 + bus_stop_panel.size[0]
        spotify_panel = build_spotify_panel(current_track, TOTAL_WIDTH - spotify_x)
        spotify_y = TOTAL_HEIGHT - energy_panel.size[1] - spotify_panel.size[1]
        img.paste(spotify_panel, (spotify_x, spotify_y))
        draw.line((spotify_x, spotify_y - 5, TOTAL_WIDTH - 10, spotify_y - 5), fill="black")

    draw.text((2, TOTAL_HEIGHT - 2), f"Updated: {datetime.now().isoformat()}", "LightGray", anchor="ld")
    print("About to display")
    epd.display(epd.getbuffer(img))
