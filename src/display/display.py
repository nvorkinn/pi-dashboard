from datetime import datetime
import sys

from PIL import Image, ImageDraw

from display.combined_arrival_panel import CombinedArrivalPanel
from display.energy_panel import EnergyPanel
from display.weather_panel import WeatherPanel
from display.spotify_panel import build_spotify_panel
from display.utils import TOTAL_WIDTH, TOTAL_HEIGHT

class DisplayController:
    def __init__(self):
        try:
            sys.path.insert(1, "./src/display/lib")
            import epd7in5_V2
            self.display_enabled = True
            self.epd = epd7in5_V2.EPD()
        except RuntimeError as e:
            print(f"Error importing epd7in5_V2: {e}")
            self.display_enabled = False
            self.epd = None

    def display_screen(self, arrival_panel: CombinedArrivalPanel, energy_panel: EnergyPanel,
                       current_track: dict[str, str] | None, weather_panel: WeatherPanel | None) -> Image.Image:
        img = Image.new("RGBA", (TOTAL_WIDTH, TOTAL_HEIGHT), (255, 255, 255, 255))

        # Arrivals
        bus_stop_panel = arrival_panel.render(TOTAL_WIDTH, 275)
        img.paste(bus_stop_panel, (5, 5), bus_stop_panel)

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
                rendered_weather = weather_panel.render(TOTAL_WIDTH - spotify_x, spotify_y)
                img.paste(rendered_weather, (spotify_x - 5, 5), rendered_weather)
        else:
            if weather_panel:
                rendered_weather = weather_panel.render(TOTAL_WIDTH - spotify_x, TOTAL_HEIGHT - energy_panel.size[1])
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

    def display_partial(self, arrival_panel: CombinedArrivalPanel, energy_panel: EnergyPanel | None,
                       current_track: dict[str, str] | None, weather_panel: WeatherPanel | None) -> Image.Image:
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

    def shutdown(self) -> None:
        if self.epd:
            self.epd.sleep()
