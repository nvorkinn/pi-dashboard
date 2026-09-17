import sys
from pathlib import Path

sys.path.insert(1, str(Path(__file__).resolve().parent / "lib"))
import epd7in5_V2
epd = epd7in5_V2.EPD()
epd.init()
epd.Clear()
epd.sleep()
print("Display cleared and put to sleep.")