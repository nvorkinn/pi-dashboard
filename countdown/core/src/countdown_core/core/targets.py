"""Where DisplayController's frames end up. The controller decides what to paint and when;
a target only knows how to get one picture onto one kind of screen."""

import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image

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
        self.dev_dir = Path(__file__).resolve().parents[4] / "dev"

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
        # The interpreter is the release venv's, which has the driver in countdown_standalone/lib.
        remote = f'cd {self.pi_dir} && "$(uv tool dir)/countdown-standalone/bin/python" pi_display.py {" ".join(args)}'
        subprocess.run([*self.SSH, self.host, f"bash -lc '{remote}'"], check=True)


def target_from_env() -> DisplayTarget:
    """DISPLAY_TARGET picks where frames go:
    - preview: the local image viewer
    - remote: a Pi over ssh (PI_HOST required, PI_DIR defaults to countdown-dev)
    - auto, or unset: the local image viewer
    The panel itself (epd) is only reachable from countdown_standalone, which has the driver."""
    choice = os.environ.get("DISPLAY_TARGET", "auto").strip().lower()
    if choice in ("preview", "auto"):
        return PreviewTarget()
    if choice == "remote":
        return RemotePiTarget.from_env()
    raise ValueError(f"Unknown DISPLAY_TARGET {choice!r}: expected preview, remote or auto")
