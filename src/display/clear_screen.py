import sys

sys.path.insert(1, "./src/display/lib")
import epd7in5_V2
epd = epd7in5_V2.EPD()
epd.init()
epd.Clear()
epd.sleep()
print("Display cleared and put to sleep.")