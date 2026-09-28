"""Runs on the Pi: python pi_display.py frame.bin -- puts the bytes on the panel.
Pass a byte-aligned region too (x0 y0 x1 y1) for a partial refresh of just that box,
or --clear instead of a frame to blank the panel."""

import importlib.util
import sys
from pathlib import Path

# The driver ships inside the installed release (countdown/lib), not as a top-level module.
sys.path.insert(1, str(Path(importlib.util.find_spec("countdown").submodule_search_locations[0]) / "lib"))
import epd7in5_V2  # noqa: E402

epd = epd7in5_V2.EPD()
if sys.argv[1] == "--clear":
    epd.init()
    epd.Clear()
else:
    buf = bytearray(Path(sys.argv[1]).read_bytes())
    if len(sys.argv) > 2:
        x0, y0, x1, y1 = (int(a) for a in sys.argv[2:6])
        epd.init_part()
        epd.display_Partial(buf, x0, y0, x1, y1)
    else:
        epd.init()
        epd.display(buf)
epd.sleep()
