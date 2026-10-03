"""The Waveshare e-paper panel: the one display target that needs the Pi's hardware, so it
lives here and not in countdown_core."""

import logging
import os
import sys
import time
from pathlib import Path

from PIL import Image

from countdown_core.core import targets
from countdown_core.core.targets import DisplayTarget, PreviewTarget, Region, panel_bytes

logger = logging.getLogger(__name__)

LIB_DIR = str(Path(__file__).resolve().parent / "lib")

# How often a panel that didn't answer is asked again, so a screen can be plugged in later.
PANEL_RETRY_INTERVAL_S = 300


class EpdTarget(DisplayTarget):
    """The Waveshare 7.5" V2 panel over SPI, on the Pi itself."""

    def __init__(self, epd):
        self.epd = epd
        self._next_probe = 0.0
        # Whether the panel is initialised and its SPI open; the driver's sleep() closes it.
        self._awake = False

    def paint(self, img: Image.Image, region: Region | None = None) -> bool:
        if region is None:
            # No Clear() first: display() overwrites every pixel, and Clear() is a full
            # refresh (an extra flash) of its own.
            if not self._wake_panel():
                return False
            self.epd.display(self.epd.getbuffer(img))
        else:
            if not self._wake_panel(self.epd.init_part):
                return False
            self.epd.display_Partial(panel_bytes(img, region), *region)
        self._sleep_panel()
        return True

    def _wake_panel(self, init=None) -> bool:
        """Initialises the panel (`init` defaults to the full-refresh init), or returns
        False if it doesn't answer the POWER ON handshake (absent, unpowered or broken). An
        absent panel isn't asked again for PANEL_RETRY_INTERVAL_S."""
        if self.connected is False and time.monotonic() < self._next_probe:
            return False
        try:
            (init or self.epd.init)()
        except RuntimeError as e:
            if self.connected is not False:
                logger.warning(
                    f"No e-paper panel responding ({e}) -- running without a display, re-checking every 5 minutes"
                )
            self.connected = False
            self._next_probe = time.monotonic() + PANEL_RETRY_INTERVAL_S
            return False
        if self.connected is False:
            logger.info("E-paper panel detected")
        self.connected = True
        self._awake = True
        return True

    def _sleep_panel(self) -> None:
        self.epd.sleep()
        self._awake = False

    def close(self) -> None:
        # Only needed if a paint was interrupted: every paint ends with the panel asleep.
        if self._awake:
            try:
                self._sleep_panel()
            except Exception as e:
                logger.warning(f"Could not put the e-paper panel to sleep: {e}", exc_info=True)


def _load_epd():
    sys.path.insert(1, LIB_DIR)
    import epd7in5_V2

    return epd7in5_V2.EPD()


def target_from_env() -> DisplayTarget:
    """DISPLAY_TARGET picks where frames go:
    - epd: the panel on this Pi (fails if the driver can't be loaded)
    - auto, or unset: the panel if the driver loads, the image viewer if not
    - anything else (preview, remote): as countdown_core's target_from_env picks it"""
    choice = os.environ.get("DISPLAY_TARGET", "auto").strip().lower()
    if choice == "epd":
        return EpdTarget(_load_epd())
    if choice != "auto":
        return targets.target_from_env()
    try:
        return EpdTarget(_load_epd())
    except (ImportError, RuntimeError) as e:
        logger.warning(f"Error importing epd7in5_V2: {e} -- previewing frames locally instead", exc_info=True)
        return PreviewTarget()
