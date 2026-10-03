from PIL import Image, ImageDraw

from countdown_core.tfl.abstract_arrival_panel import ROW_GAP, AbstractArrivalPanel
from countdown_core.tfl.models import MetroStopPoint, TubeArrival
from countdown_core.utils.utils import ROUNDEL


class TubeArrivalPanel(AbstractArrivalPanel):
    def __init__(self, stop: MetroStopPoint, arrivals: list[TubeArrival]):
        super().__init__([a for a in arrivals if a.naptan_id != a.destination_naptan_id])
        self.stop = stop

    def add_header(self, img: Image.Image, draw: ImageDraw.ImageDraw) -> None:
        img.paste(ROUNDEL, (5, 2), ROUNDEL)
        station = self.stop.common_name.removesuffix(" Underground Station")
        draw.text((10 + ROUNDEL.size[0], 10), station, "white", font_size=15, anchor="lm")

    def _create_panel_for_arrivals(self, arrivals: list[TubeArrival], max_x: int, max_y: int) -> Image.Image:
        img = Image.new("RGBA", (max_x, max_y), (255, 255, 255, 0))
        y = 0
        for arrival in arrivals:
            arrival_string = self._get_time_text(arrival.time_to_station // 60)
            arrival_panel = self._create_panel_for_stop_arrival(arrival.line[0], arrival.towards, arrival_string, max_x)
            arrival_panel_bottom = y + arrival_panel.size[1]
            if arrival_panel_bottom > img.size[1]:
                return img
            img.paste(arrival_panel, (0, y))
            y = arrival_panel_bottom + ROW_GAP
        return img

    @staticmethod
    def _limit_arrivals_per_line(arrivals: list[TubeArrival], line_count: int) -> list[TubeArrival]:
        match line_count:
            case x if x <= 1:
                return arrivals
            case 2:
                return arrivals[:4]
            case 3:
                return arrivals[:3]
            case _:
                return arrivals[:1]
