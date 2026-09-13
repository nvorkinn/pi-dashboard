from collections import defaultdict

from PIL import Image, ImageDraw

from countdown.models import TubeArrival, MetroStopPoint
from display.abstract_arrival_panel import AbstractArrivalPanel
from display.utils import TFL_FONT_15, ROUNDEL, TFL_MEDIUM_FONT_10

class TubeArrivalPanel(AbstractArrivalPanel):
    def __init__(self, stop: MetroStopPoint, arrivals: list[TubeArrival]):
        super().__init__()
        self.stop = stop
        # Remove arrivals that are going to the same station as the stop
        self.arrivals = [a for a in arrivals if a.naptan_id != a.destination_naptan_id]

    def render(self) -> Image.Image:
        img = Image.new("RGBA", (230, 275), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        draw.font = TFL_FONT_15
        draw.rounded_rectangle((0, 0, img.size[0], 20), 10, "black")
        img.paste(ROUNDEL, (5, 2), ROUNDEL)
        station = self.stop.common_name.removesuffix(" Underground Station")
        draw.text((10 + ROUNDEL.size[0], 10), station, "white", anchor="lm")
        img.paste(self._create_panel_for_tube_arrivals(self.arrivals, img.size[0], img.size[1] - 25), (0, 25))
        return img

    def _create_panel_for_tube_arrivals(self, arrivals: list[TubeArrival], max_x: int, max_y: int) -> Image.Image:
        img = Image.new("RGBA", (max_x, max_y), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        draw.font = TFL_MEDIUM_FONT_10
        arrivals_by_line = self._categorise_arrivals_by_line(arrivals)
        y = 0
        for line, departures in arrivals_by_line.items():
            if len(arrivals_by_line) > 1:
                draw.text((0, y), line, "#48494B", anchor="la")
                y += 11
            for departure in self._limit_arrivals_per_line(departures, len(arrivals_by_line)):
                arrival_string = self._get_time_text(departure.time_to_station // 60)
                departure_panel = self._create_panel_for_stop_departure(
                    departure.line[0], departure.towards, arrival_string, max_x)
                departure_panel_bottom = y + departure_panel.size[1]
                if departure_panel_bottom > img.size[1]:
                    return img
                img.paste(departure_panel, (0, y))
                y = departure_panel_bottom + 3
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

    @staticmethod
    def _categorise_arrivals_by_line(arrivals: list[TubeArrival]) -> dict[str, list[TubeArrival]]:
        arrivals_by_line = defaultdict(list)
        for arrival in arrivals:
            arrivals_by_line[arrival.line].append(arrival)
        return arrivals_by_line