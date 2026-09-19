import sys
import time
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

# How long to leave it before asking a panel that didn't answer whether it's there yet,
# so plugging a screen in later just works, without a restart.
PANEL_RETRY_INTERVAL_S = 300


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
        # None until the panel's first been asked (or if there's no driver at all); then
        # whether it answered. Only meaningful when display_enabled: a machine with no
        # driver at all previews via img.show() instead, and never asks a panel anything.
        self.panel_connected: bool | None = None
        self._next_probe = 0.0

    def _wake_panel(self) -> bool:
        """Initialises the panel, or returns False if it doesn't answer -- no screen
        connected (or powered), which init() finds out via the POWER ON handshake, and
        which can't be told apart from a connected one that's broken. Once a panel's
        known to be absent it isn't asked again until PANEL_RETRY_INTERVAL_S has passed,
        so a Pi running without a display neither waits on it every cycle nor spams the
        log; it's said once when the answer changes."""
        if self.panel_connected is False and time.monotonic() < self._next_probe:
            return False
        try:
            self.epd.init()
        except RuntimeError as e:
            if self.panel_connected is not False:
                print(f"No e-paper panel responding ({e}) -- running without a display, re-checking every 5 minutes")
            self.panel_connected = False
            self._next_probe = time.monotonic() + PANEL_RETRY_INTERVAL_S
            return False
        if self.panel_connected is False:
            print("E-paper panel detected")
        self.panel_connected = True
        return True

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
            if self._wake_panel():
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
            if self._wake_panel():
                self.epd.Clear()
                self.epd.display(self.epd.getbuffer(img))
                self.epd.sleep()
            else:
                # Called only when the code changes, so this is once per code. Without it a
                # Pi with no screen can't be paired at all: nothing else is published or
                # polled while a code is pending.
                print(
                    f"No display to show the pairing code on -- it is {panel.pairing_code} (device {panel.device_id})"
                )
        else:
            img.show()

        return img

    def shutdown(self) -> None:
        # Only a panel known to be awake needs putting to sleep; asking one that never
        # answered would just wait out the busy timeout.
        if self.epd and self.panel_connected:
            try:
                self.epd.sleep()
            except RuntimeError as e:
                print(f"Could not put the e-paper panel to sleep: {e}")
