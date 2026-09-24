import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from countdown.api_registry import ClientClasses
from display.combined_arrival_panel import CombinedArrivalPanel
from display.empty_panel import EmptyPanel
from display.pairing_code_panel import PairingCodePanel
from display.panel import Panel
from display.setup_panel import SetupPanel
from display.utils import TOTAL_HEIGHT, TOTAL_WIDTH

logger = logging.getLogger(__name__)

LIB_DIR = str(Path(__file__).resolve().parent / "lib")

# How long to leave it before asking a panel that didn't answer whether it's there yet,
# so plugging a screen in later just works, without a restart.
PANEL_RETRY_INTERVAL_S = 300

# A partial refresh is quick and doesn't flash, but each one leaves a little ghosting
# behind, so once this long has passed since the last full refresh the next change is
# repainted in full. Also the most often the screen flashes: the arrivals change about
# once a minute, everything else far less.
FULL_REFRESH_INTERVAL_S = 600

# Where display_screen() puts the arrivals panel, the part of the screen that changes
# every minute and so the only part worth a partial refresh.
ARRIVALS_ORIGIN = (5, 5)
ARRIVALS_HEIGHT = 275


class DisplayController:
    def __init__(self):
        try:
            sys.path.insert(1, LIB_DIR)
            import epd7in5_V2

            self.display_enabled = True
            self.epd = epd7in5_V2.EPD()
        except (ImportError, RuntimeError) as e:
            logger.warning(f"Error importing epd7in5_V2: {e}", exc_info=True)
            self.display_enabled = False
            self.epd = None
        # None until the panel's first been asked (or if there's no driver at all); then
        # whether it answered. Only meaningful when display_enabled: a machine with no
        # driver at all previews via img.show() instead, and never asks a panel anything.
        self.panel_connected: bool | None = None
        self._next_probe = 0.0
        # What's on the panel right now (minus the "Updated:" footer), so an unchanged
        # picture isn't repainted and a changed arrivals panel can be refreshed alone.
        # None whenever that isn't known -- nothing painted yet, or the last paint failed.
        self._shown: Image.Image | None = None
        self._last_full_refresh = 0.0
        # A whole-screen picture (pairing code, checklist, splash) the panel couldn't take yet.
        self._pending: Image.Image | None = None
        # Whether the panel is initialised and its SPI open; the driver's sleep() closes it.
        self._awake = False

    def _wake_panel(self, init=None) -> bool:
        """Initialises the panel (`init` defaults to the full-refresh init), or returns
        False if it doesn't answer -- no screen connected (or powered), which init() finds
        out via the POWER ON handshake, and which can't be told apart from a connected one
        that's broken. Once a panel's known to be absent it isn't asked again until
        PANEL_RETRY_INTERVAL_S has passed, so a Pi running without a display neither waits
        on it every cycle nor spams the log; it's said once when the answer changes."""
        if self.panel_connected is False and time.monotonic() < self._next_probe:
            return False
        try:
            (init or self.epd.init)()
        except RuntimeError as e:
            if self.panel_connected is not False:
                logger.warning(
                    f"No e-paper panel responding ({e}) -- running without a display, re-checking every 5 minutes"
                )
            self.panel_connected = False
            self._next_probe = time.monotonic() + PANEL_RETRY_INTERVAL_S
            return False
        if self.panel_connected is False:
            logger.info("E-paper panel detected")
        self.panel_connected = True
        self._awake = True
        return True

    def display_screen(self, panels: dict[str, Panel | None]) -> Image.Image:
        """Composes whatever panels the registry has and puts it on the panel only if it
        changed: not at all if the picture is the same, as a quick partial refresh if only
        the arrivals changed, otherwise as a full refresh (which flashes). A missing/None
        panel just leaves its slot empty (no stops configured, Glowmarkt not set up,
        nothing playing, weather not fetched yet) rather than failing the whole screen --
        unless there's nothing at all, which shows a "nothing to show yet" message."""
        img, arrivals_box = self._compose(panels)
        content = img.convert("RGB")
        # Drawn after `content` is taken, so it never counts as a change: it's only as
        # current as the last repaint.
        ImageDraw.Draw(img).text(
            (2, TOTAL_HEIGHT - 2), f"Updated: {datetime.now().isoformat()}", "LightGray", anchor="ld"
        )
        self._show(img, content, arrivals_box)
        return img

    def _compose(self, panels: dict[str, Panel | None]) -> tuple[Image.Image, tuple[int, int, int, int] | None]:
        """The screen without its footer, and the box the arrivals panel occupies (None
        when it's the whole-screen "nothing to show" message)."""
        img = Image.new("RGBA", (TOTAL_WIDTH, TOTAL_HEIGHT), (255, 255, 255, 255))

        # Arrivals
        arrival_panel = panels.get(ClientClasses.TFL.api_name) or CombinedArrivalPanel([])
        bus_stop_panel = arrival_panel.render(TOTAL_WIDTH, ARRIVALS_HEIGHT)
        others = [ClientClasses.GLOWMARKT, ClientClasses.WEATHER, ClientClasses.SPOTIFY]
        if bus_stop_panel.size[0] == 0 and not any(panels.get(client.api_name) for client in others):
            return EmptyPanel().render(TOTAL_WIDTH, TOTAL_HEIGHT), None
        img.paste(bus_stop_panel, ARRIVALS_ORIGIN, bus_stop_panel)
        arrivals_box = (
            ARRIVALS_ORIGIN[0],
            ARRIVALS_ORIGIN[1],
            ARRIVALS_ORIGIN[0] + bus_stop_panel.size[0],
            ARRIVALS_ORIGIN[1] + bus_stop_panel.size[1],
        )

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

        return img, arrivals_box

    def _show(self, img: Image.Image, content: Image.Image, arrivals_box) -> None:
        if not (self.display_enabled and self.epd):
            img.show()
            return

        changed = ImageChops.difference(self._shown, content).getbbox() if self._shown is not None else None
        if self._shown is not None and changed is None:
            return  # this exact picture is already on the panel

        self._pending = None  # the dashboard supersedes any screen still waiting for the panel
        region = self._partial_region(changed, arrivals_box)
        now = time.monotonic()
        try:
            if region is not None and now - self._last_full_refresh < FULL_REFRESH_INTERVAL_S:
                painted = self._refresh_partial(img, region)
            else:
                painted = self._refresh_full(img)
                if painted:
                    self._last_full_refresh = now
        except Exception:
            self._shown = None  # can't know what state the panel was left in
            raise
        self._shown = content if painted else None

    @staticmethod
    def _partial_region(changed, arrivals_box) -> tuple[int, int, int, int] | None:
        """The byte-aligned box to partially refresh, or None if that isn't enough: no
        picture to compare with yet, or something outside the arrivals changed. (A wider or
        narrower arrivals panel shifts everything beside it, so that lands here too.)"""
        if changed is None or arrivals_box is None:
            return None
        ax0, ay0, ax1, ay1 = arrivals_box
        if changed[0] < ax0 or changed[1] < ay0 or changed[2] > ax1 or changed[3] > ay1:
            return None
        return (0, ay0, -(-ax1 // 8) * 8, ay1)  # x in whole bytes (8 pixels), as the panel needs

    def _refresh_full(self, img: Image.Image) -> bool:
        # No Clear() first: display() overwrites every pixel itself, so Clear() only added a
        # whole extra black-and-white flash (it is a full refresh of its own).
        if not self._wake_panel():
            return False
        self.epd.display(self.epd.getbuffer(img))
        self._sleep_panel()
        return True

    def _refresh_partial(self, img: Image.Image, region: tuple[int, int, int, int]) -> bool:
        if not self._wake_panel(self.epd.init_part):
            return False
        x0, y0, x1, y1 = region
        buf = bytearray(img.crop(region).convert("1").tobytes("raw"))
        for i in range(len(buf)):
            buf[i] ^= 0xFF
        self.epd.display_Partial(buf, x0, y0, x1, y1)
        self._sleep_panel()
        return True

    def _paint_whole_screen(self, img: Image.Image) -> bool:
        """For the screens that replace the picture outright (pairing code, splash) rather
        than composing panels. False if there's no panel to paint on."""
        # Whatever was on the panel is about to be replaced, so the next normal screen has
        # to be painted in full even if it matches one shown before.
        self._shown = None
        self._pending = img
        if not self._wake_panel():
            return False
        self.epd.display(self.epd.getbuffer(img))
        self._sleep_panel()
        self._pending = None
        return True

    def repaint_pending(self) -> None:
        """Retries a whole-screen picture that couldn't be painted (no panel yet, or the paint
        failed), so it appears once the panel does instead of waiting for its state to change."""
        if self._pending is not None and self.display_enabled and self.epd:
            self._paint_whole_screen(self._pending)

    def display_pairing_screen(self, panel: PairingCodePanel) -> Image.Image:
        img = panel.render(TOTAL_WIDTH, TOTAL_HEIGHT)

        if self.display_enabled and self.epd:
            if not self._paint_whole_screen(img):
                # Called only when the code changes, so this is once per code. Without it a
                # Pi with no screen can't be paired at all: nothing else is published or
                # polled while a code is pending.
                logger.warning(
                    f"No display to show the pairing code on -- it is {panel.pairing_code} (device {panel.device_id})"
                )
        else:
            img.show()

        return img

    def display_setup_screen(self, panel: SetupPanel) -> Image.Image:
        img = panel.render(TOTAL_WIDTH, TOTAL_HEIGHT)

        if self.display_enabled and self.epd:
            if not self._paint_whole_screen(img):
                logger.warning(f"No display to show the setup checklist on -- still needed: {', '.join(panel.missing)}")
        else:
            img.show()

        return img

    def display_splash(self, panel: Panel) -> Image.Image:
        """The "can't reach the server" screen shown at boot. Painted once by the caller,
        not on every retry -- it's a full refresh."""
        img = panel.render(TOTAL_WIDTH, TOTAL_HEIGHT)

        if self.display_enabled and self.epd:
            self._paint_whole_screen(img)
        else:
            img.show()

        return img

    def _sleep_panel(self) -> None:
        self.epd.sleep()
        self._awake = False

    def shutdown(self) -> None:
        # Every paint ends with the panel asleep and its SPI closed, so this only has work to
        # do if a paint was interrupted. It runs inside the SIGTERM handler, so it can't raise.
        if self.epd and self._awake:
            try:
                self._sleep_panel()
            except Exception as e:
                logger.warning(f"Could not put the e-paper panel to sleep: {e}", exc_info=True)
