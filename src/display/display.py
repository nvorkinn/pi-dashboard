import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from countdown.api_registry import ClientClasses
from display.combined_arrival_panel import CombinedArrivalPanel
from display.energy_panel import EnergyPanel
from display.pairing_code_panel import PairingCodePanel
from display.panel import Panel
from display.spotify_panel import build_spotify_panel
from display.utils import TOTAL_HEIGHT, TOTAL_WIDTH
from display.weather_panel import WeatherPanel

LIB_DIR = str(Path(__file__).resolve().parent / "lib")


class DisplayController:
    def __init__(self):
        try:
            sys.path.insert(1, LIB_DIR)
            import epd7in5_V2

            self.display_enabled = True
            self.epd = epd7in5_V2.EPD()
        except (ImportError, RuntimeError) as e:
            print(f"Error importing epd7in5_V2: {e}")
            self.display_enabled = False
            self.epd = None

    def display_screen(self, panels: dict[str, Panel | None]) -> Image.Image:
        """Composes whatever panels the registry has. A missing/None panel just leaves
        its slot empty (no stops configured, Glowmarkt not set up, nothing playing,
        weather not fetched yet) rather than failing the whole screen."""
        img = Image.new("RGBA", (TOTAL_WIDTH, TOTAL_HEIGHT), (255, 255, 255, 255))

        # Arrivals
        arrival_panel = panels.get(ClientClasses.TFL.api_name) or CombinedArrivalPanel([])
        bus_stop_panel = arrival_panel.render(TOTAL_WIDTH, 275)
        img.paste(bus_stop_panel, (5, 5), bus_stop_panel)

        energy_height = 0
        energy_panel = panels.get(ClientClasses.GLOWMARKT.api_name)
        if energy_panel:
            rendered_energy = energy_panel.render(TOTAL_WIDTH, 200)
            energy_height = rendered_energy.size[1]
            img.paste(rendered_energy, (0, TOTAL_HEIGHT - energy_height))

        draw = ImageDraw.Draw(img)
        spotify_x = 10 + bus_stop_panel.size[0]
        weather_panel = panels.get(ClientClasses.WEATHER.api_name)
        spotify_panel = panels.get(ClientClasses.SPOTIFY.api_name)
        weather_height = TOTAL_HEIGHT - energy_height
        if spotify_panel:
            rendered_spotify = spotify_panel.render(TOTAL_WIDTH - spotify_x, 0)
            spotify_y = TOTAL_HEIGHT - energy_height - rendered_spotify.size[1]
            img.paste(rendered_spotify, (spotify_x, spotify_y))
            draw.line((spotify_x, spotify_y - 5, TOTAL_WIDTH - 10, spotify_y - 5), fill="black")
            weather_height = spotify_y
        if weather_panel:
            rendered_weather = weather_panel.render(TOTAL_WIDTH - spotify_x, weather_height)
            img.paste(rendered_weather, (spotify_x - 5, 5), rendered_weather)

        draw.text((2, TOTAL_HEIGHT - 2), f"Updated: {datetime.now().isoformat()}", "LightGray", anchor="ld")

        if self.display_enabled and self.epd:
            self.epd.init()
            self.epd.Clear()
            self.epd.display(self.epd.getbuffer(img))
            self.epd.sleep()
        else:
            img.show()

        return img

    def display_partial(
        self,
        arrival_panel: CombinedArrivalPanel,
        energy_panel: EnergyPanel | None,
        current_track: dict[str, str] | None,
        weather_panel: WeatherPanel | None,
    ) -> Image.Image:
        img = Image.new("RGBA", (TOTAL_WIDTH, TOTAL_HEIGHT), (255, 255, 255, 255))

        # Arrivals
        bus_stop_panel = arrival_panel.render(TOTAL_WIDTH, 275)
        img.paste(bus_stop_panel, (5, 5), bus_stop_panel)

        if energy_panel:
            energy_panel = energy_panel.render(TOTAL_WIDTH, 200)
            img.paste(energy_panel, (0, TOTAL_HEIGHT - energy_panel.size[1]))

        draw = ImageDraw.Draw(img)
        spotify_x = 10 + bus_stop_panel.size[0]
        if current_track:
            spotify_panel = build_spotify_panel(current_track, TOTAL_WIDTH - spotify_x)
            spotify_y = TOTAL_HEIGHT - energy_panel.size[1] - spotify_panel.size[1]
            img.paste(spotify_panel, (spotify_x, spotify_y))
            draw.line((spotify_x, spotify_y - 5, TOTAL_WIDTH - 10, spotify_y - 5), fill="black")
            if weather_panel:
                weather_panel = weather_panel.render(TOTAL_WIDTH - spotify_x, spotify_y)
                img.paste(weather_panel, (spotify_x - 5, 5), weather_panel)
        else:
            if weather_panel:
                weather_panel = weather_panel.render(TOTAL_WIDTH - spotify_x, TOTAL_HEIGHT - energy_panel.size[1])
                img.paste(weather_panel, (spotify_x - 5, 5), weather_panel)

        if self.display_enabled and self.epd:
            self.epd.init_part()
            x_start = 0
            y_start = 5
            x_end = (bus_stop_panel.size[0] + 9) // 8 * 8  # round up to nearest multiple of 8
            y_end = bus_stop_panel.size[1] + 5

            cropped = img.crop((x_start, y_start, x_end, y_end)).convert("1")
            buf = bytearray(cropped.tobytes("raw"))
            for i in range(len(buf)):
                buf[i] ^= 0xFF

            self.epd.display_Partial(buf, 0, 5, bus_stop_panel.size[0] + 9, bus_stop_panel.size[1] + 5)
            self.epd.sleep()
        else:
            img.show()

        return img

    def display_pairing_screen(self, panel: PairingCodePanel) -> Image.Image:
        img = panel.render(TOTAL_WIDTH, TOTAL_HEIGHT)

        if self.display_enabled and self.epd:
            self.epd.init()
            self.epd.Clear()
            self.epd.display(self.epd.getbuffer(img))
            self.epd.sleep()
        else:
            img.show()

        return img

    def shutdown(self) -> None:
        if self.epd:
            self.epd.sleep()
