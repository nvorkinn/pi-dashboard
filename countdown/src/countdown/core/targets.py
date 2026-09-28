"""Where DisplayController's frames end up. The controller decides what to paint and when;
a target only knows how to get one picture onto one kind of screen."""

import logging
import os
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

LIB_DIR = str(Path(__file__).resolve().parents[1] / "lib")

# How often a panel that didn't answer is asked again, so a screen can be plugged in later.
PANEL_RETRY_INTERVAL_S = 300

Region = tuple[int, int, int, int]


class DisplayTarget(ABC):
    # Whether the screen answered; None until known (or for targets that can't tell).
    connected: bool | None = None

    @abstractmethod
    def paint(self, img: Image.Image, region: Region | None = None) -> bool:
        """Puts the full 800x480 `img` on the screen -- or with a (byte-aligned) region,
        just that part of it, as a partial refresh. False if there's no screen to take it."""

    def close(self) -> None:  # noqa: B027 -- optional hook: only a target holding hardware needs it
        """Called at shutdown, from inside the SIGTERM handler, so it mustn't raise."""


def panel_bytes(img: Image.Image, region: Region | None = None) -> bytearray:
    """The picture (or the region of it) as the panel's raw 1-bit buffer. The bytes need
    inverting: in the PIL world 0=black and 1=white, on the e-paper 0=white and 1=black."""
    if region is not None:
        img = img.crop(region)
    buf = bytearray(img.convert("1").tobytes("raw"))
    for i in range(len(buf)):
        buf[i] ^= 0xFF
    return buf


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


class PreviewTarget(DisplayTarget):
    """Opens each new frame in the local image viewer -- for a machine with no panel."""

    def paint(self, img: Image.Image, region: Region | None = None) -> bool:
        img.show()  # the whole picture even for a partial: a viewer has nothing to update in place
        return True


class RemotePiTarget(DisplayTarget):
    """Dev only: rsyncs each frame to a Pi and runs dev/pi_display.py there (see README)."""

    SSH = ["ssh", "-o", "ControlMaster=auto", "-o", "ControlPath=/tmp/pi-dev-%C", "-o", "ControlPersist=120"]

    def __init__(self, host: str, pi_dir: str = "countdown-dev"):
        if not host:
            raise ValueError("RemotePiTarget needs a host (PI_HOST, e.g. nikolai@countdown.local)")
        self.host = host
        self.pi_dir = pi_dir
        self.dev_dir = Path(__file__).resolve().parents[3] / "dev"

    @classmethod
    def from_env(cls) -> RemotePiTarget:
        return cls(os.environ.get("PI_HOST", ""), os.environ.get("PI_DIR", "countdown-dev"))

    def paint(self, img: Image.Image, region: Region | None = None) -> bool:
        frame = self.dev_dir / "out" / "frame.bin"
        frame.parent.mkdir(exist_ok=True)
        frame.write_bytes(bytes(panel_bytes(img, region)))
        self._run_pi_display(frame.name, *map(str, region or ()), extra_files=(frame,))
        return True

    def clear(self) -> None:
        """Blanks the panel (a full refresh to white)."""
        self._run_pi_display("--clear")

    def _run_pi_display(self, *args: str, extra_files: tuple[Path, ...] = ()) -> None:
        """Copies dev/pi_display.py (and `extra_files`) to the Pi and runs it there with `args`."""
        subprocess.run(
            [
                "rsync",
                "-az",
                "-e",
                " ".join(self.SSH),
                *map(str, extra_files),
                str(self.dev_dir / "pi_display.py"),
                f"{self.host}:{self.pi_dir}/",
            ],
            check=True,
        )
        # The interpreter is the release venv's, which has the driver in countdown/lib.
        remote = f'cd {self.pi_dir} && "$(uv tool dir)/countdown/bin/python" pi_display.py {" ".join(args)}'
        subprocess.run([*self.SSH, self.host, f"bash -lc '{remote}'"], check=True)


def _load_epd():
    sys.path.insert(1, LIB_DIR)
    import epd7in5_V2

    return epd7in5_V2.EPD()


def target_from_env() -> DisplayTarget:
    """DISPLAY_TARGET picks where frames go:
    - epd: the panel on this Pi (fails if the driver can't be loaded)
    - preview: the local image viewer
    - remote: a Pi over ssh (PI_HOST required, PI_DIR defaults to countdown-dev)
    - auto, or unset: the panel if the driver loads, the image viewer if not"""
    choice = os.environ.get("DISPLAY_TARGET", "auto").strip().lower()
    if choice == "epd":
        return EpdTarget(_load_epd())
    if choice == "preview":
        return PreviewTarget()
    if choice == "remote":
        return RemotePiTarget.from_env()
    if choice != "auto":
        raise ValueError(f"Unknown DISPLAY_TARGET {choice!r}: expected epd, preview, remote or auto")
    try:
        return EpdTarget(_load_epd())
    except (ImportError, RuntimeError) as e:
        logger.warning(f"Error importing epd7in5_V2: {e} -- previewing frames locally instead", exc_info=True)
        return PreviewTarget()
