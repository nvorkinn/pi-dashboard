from datetime import datetime
import sys

from PIL import Image, ImageDraw

from display.combined_arrival_panel import CombinedArrivalPanel
from display.energy_panel import EnergyPanel
from display.spotify_panel import build_spotify_panel
from display.utils import add_border, TOTAL_WIDTH, TOTAL_HEIGHT

class DisplayController:
    def __init__(self):
        try:
            sys.path.insert(1, "./lib")
            import epd7in5_V2
            self.display_enabled = True
            self.epd = epd7in5_V2.EPD()
        except ImportError:
            print("Error importing epd7in5_V2")
            self.display_enabled = False

    def display_screen(self, arrival_panel: CombinedArrivalPanel, energy_panel: EnergyPanel, current_track: dict[str, str] | None) -> None:
        img = Image.new("RGBA", (TOTAL_WIDTH, TOTAL_HEIGHT), (255, 255, 255, 255))

        # Departures
        bus_stop_panel = arrival_panel.render()
        img.paste(bus_stop_panel, (5, 5), bus_stop_panel)

        energy_panel = energy_panel.render()
        img.paste(energy_panel, (0, TOTAL_HEIGHT - energy_panel.size[1]))

        draw = ImageDraw.Draw(img)
        if current_track:
            spotify_x = 10 + bus_stop_panel.size[0]
            spotify_panel = build_spotify_panel(current_track, TOTAL_WIDTH - spotify_x)
            spotify_y = TOTAL_HEIGHT - energy_panel.size[1] - spotify_panel.size[1]
            img.paste(spotify_panel, (spotify_x, spotify_y))
            draw.line((spotify_x, spotify_y - 5, TOTAL_WIDTH - 10, spotify_y - 5), fill="black")

        draw.text((2, TOTAL_HEIGHT - 2), f"Updated: {datetime.now().isoformat()}", "LightGray", anchor="ld")
        add_border(img)

        if self.display_enabled:
            self.epd.init()
            self.epd.Clear()
            self.epd.display(self.epd.getbuffer(img))
            self.epd.sleep()
        else:
            img.show()

    def shutdown(self) -> None:
        self.epd.sleep()