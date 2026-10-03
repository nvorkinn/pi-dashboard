from PIL import Image, ImageDraw

from countdown_core.tfl.abstract_arrival_panel import ROW_GAP, AbstractArrivalPanel
from countdown_core.tfl.models import BusArrival, SingleStopPoint


class BusArrivalPanel(AbstractArrivalPanel):
    def __init__(self, stop: SingleStopPoint, arrivals: list[BusArrival]):
        super().__init__(arrivals)
        self.stop = stop

    def add_header(self, img: Image.Image, draw: ImageDraw.ImageDraw) -> None:
        draw.text((7, 10), self.stop.common_name, "white", font_size=15, anchor="lm")
        draw.text((img.size[0] - 9, 10), self.stop.stop_letter, "white", anchor="rm", stroke_width=0.2)

    def _create_panel_for_arrivals(self, arrivals: list[BusArrival], max_x: int, max_y: int) -> Image.Image:
        img = Image.new("RGBA", (max_x, max_y), (255, 255, 255, 0))
        y = 0
        for arrival in arrivals:
            arrival_string = self._get_time_text(arrival.time_to_station // 60)
            arrival_panel = self._create_panel_for_stop_arrival(
                arrival.line, arrival.destination, arrival_string, max_x
            )
            arrival_panel_bottom = y + arrival_panel.size[1]
            if arrival_panel_bottom > img.size[1]:
                return img
            img.paste(arrival_panel, (0, y))
            y = arrival_panel_bottom + ROW_GAP
        return img
