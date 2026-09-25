import logging
import time

from PIL import Image, ImageChops

from countdown.api_registry import ClientClasses
from countdown.display_composers import DEFAULT_COMPOSER, choose_composer
from display.empty_panel import EmptyPanel
from display.message_panel import MessagePanel
from display.pairing_code_panel import PairingCodePanel
from display.panel import Panel
from display.setup_panel import SetupPanel
from display.targets import DisplayTarget, target_from_env
from display.utils import TOTAL_HEIGHT, TOTAL_WIDTH

logger = logging.getLogger(__name__)

# A partial refresh is quick and doesn't flash, but each one leaves a little ghosting
# behind, so once this long has passed since the last full refresh the next change is
# repainted in full. Also the most often the screen flashes: the arrivals change about
# once a minute, everything else far less.
FULL_REFRESH_INTERVAL_S = 600


class DisplayController:
    def __init__(self, target: DisplayTarget | None = None):
        # Where frames actually go: the e-paper panel, a local preview or a Pi over ssh.
        self.target = target if target is not None else target_from_env()
        # What's on the screen right now (minus the "Updated:" footer), so an unchanged
        # picture isn't repainted and a changed arrivals panel can be refreshed alone.
        # None whenever that isn't known -- nothing painted yet, or the last paint failed.
        self._shown: Image.Image | None = None
        self._last_full_refresh = 0.0
        # A whole-screen picture (pairing code, checklist, splash) the screen couldn't take yet.
        self._pending: Image.Image | None = None
        # The layout: the full one until use_layout() learns what this device can show.
        self._composer = DEFAULT_COMPOSER

    @property
    def panel_connected(self) -> bool | None:
        """None until the target has been asked (or if it can't tell, like a preview); then
        whether the panel answered."""
        return self.target.connected

    def use_layout(self, available: frozenset[ClientClasses]) -> None:
        """Picks the layout for a device that can show `available` (see
        ApiRegistry.available), called whenever the config changes. A new layout moves
        panels outside the arrivals, so the next screen is a full refresh on its own."""
        composer = choose_composer(available)
        if type(composer) is not type(self._composer):
            logger.info(f"Changing layout from: {type(self._composer).__name__} to {type(composer).__name__}")
        self._composer = composer

    def display_screen(self, panels: dict[str, Panel]) -> Image.Image:
        """Composes the registry's panels, one per API, and puts it on the panel only if it
        changed: not at all if the picture is the same, as a quick partial refresh if only
        the arrivals changed, otherwise as a full refresh (which flashes). An API with
        nothing to draw has a MessagePanel saying why (not configured, couldn't connect,
        nothing playing) -- unless none has anything, which shows a "nothing to show yet"
        message instead."""
        if all(isinstance(panel, MessagePanel) for panel in panels.values()):
            img, arrivals_box = EmptyPanel().render(TOTAL_WIDTH, TOTAL_HEIGHT), None
        else:
            img, arrivals_box = self._composer.compose(panels)
        content = img.convert("RGB")
        self._show(img, content, arrivals_box)
        return img

    def _show(self, img: Image.Image, content: Image.Image, arrivals_box) -> None:
        changed = ImageChops.difference(self._shown, content).getbbox() if self._shown is not None else None
        if self._shown is not None and changed is None:
            return  # this exact picture is already on the panel

        self._pending = None  # the dashboard supersedes any screen still waiting for the panel
        region = self._partial_region(changed, arrivals_box)
        now = time.monotonic()
        try:
            if region is not None and now - self._last_full_refresh < FULL_REFRESH_INTERVAL_S:
                painted = self.target.paint(img, region)
            else:
                painted = self.target.paint(img)
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

    def _paint_whole_screen(self, img: Image.Image) -> bool:
        """For the screens that replace the picture outright (pairing code, splash) rather
        than composing panels. False if there's no screen to paint on."""
        # Whatever was on the screen is about to be replaced, so the next normal screen has
        # to be painted in full even if it matches one shown before.
        self._shown = None
        self._pending = img
        if not self.target.paint(img):
            return False
        self._pending = None
        return True

    def repaint_pending(self) -> None:
        """Retries a whole-screen picture that couldn't be painted (no panel yet, or the paint
        failed), so it appears once the panel does instead of waiting for its state to change."""
        if self._pending is not None:
            self._paint_whole_screen(self._pending)

    def display_pairing_screen(self, panel: PairingCodePanel) -> Image.Image:
        img = panel.render(TOTAL_WIDTH, TOTAL_HEIGHT)
        if not self._paint_whole_screen(img):
            # Called only when the code changes, so this is once per code. Without it a
            # Pi with no screen can't be paired at all: nothing else is published or
            # polled while a code is pending.
            logger.warning(
                f"No display to show the pairing code on -- it is {panel.pairing_code} (device {panel.device_id})"
            )
        return img

    def display_setup_screen(self, panel: SetupPanel) -> Image.Image:
        img = panel.render(TOTAL_WIDTH, TOTAL_HEIGHT)
        if not self._paint_whole_screen(img):
            logger.warning(f"No display to show the setup checklist on -- still needed: {', '.join(panel.missing)}")
        return img

    def display_splash(self, panel: Panel) -> Image.Image:
        """The "can't reach the server" screen shown at boot. Painted once by the caller,
        not on every retry -- it's a full refresh."""
        img = panel.render(TOTAL_WIDTH, TOTAL_HEIGHT)
        self._paint_whole_screen(img)
        return img

    def shutdown(self) -> None:
        # Runs inside the SIGTERM handler; targets' close() never raises.
        self.target.close()
