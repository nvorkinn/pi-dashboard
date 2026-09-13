from PIL import Image, ImageDraw

from countdown.models import SingleStopPoint, BusArrival
from display.abstract_arrival_panel import AbstractArrivalPanel
from display.utils import TFL_FONT_15

class BusArrivalPanel(AbstractArrivalPanel):
    def __init__(self, stop: SingleStopPoint, arrivals: list[BusArrival]):
        super().__init__()
        self.stop = stop
        self.arrivals = arrivals

    def render(self) -> Image.Image:
        img = Image.new("RGBA", (230, 275), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        draw.font = TFL_FONT_15
        draw.rounded_rectangle((0, 0, img.size[0], 20), 10, "black")
        draw.text((7, 10), self.stop.common_name or "Error", "white", anchor="lm")
        draw.text((img.size[0] - 9, 10), self.stop.stop_letter, "white", anchor="rm", stroke_width=0.2)
        img.paste(self._create_panel_for_stop_departures(self.arrivals, img.size[0], img.size[1] - 25), (0, 25))
        return img

    def _create_panel_for_stop_departures(self, departures: list[BusArrival], max_x: int, max_y: int) -> Image.Image:
        img = Image.new("RGBA", (max_x, max_y), (255, 255, 255, 0))
        y = 0
        for departure in departures:
            arrival_string = self._get_time_text(departure.time_to_station // 60)
            departure_panel = self._create_panel_for_stop_departure(
                departure.line, departure.destination, arrival_string, max_x)
            departure_panel_bottom = y + departure_panel.size[1]
            if departure_panel_bottom > img.size[1]:
                return img
            img.paste(departure_panel, (0, y))
            y = departure_panel_bottom + 3
        return img