from abc import abstractmethod, ABC

from PIL import Image, ImageDraw

from countdown.models import ArrivalUnion
from display.panel import Panel
from display.utils import TFL_FONT_12, TFL_FONT_15, TFL_MEDIUM_FONT_16


class AbstractArrivalPanel(Panel, ABC):
    def __init__(self, arrivals: list[ArrivalUnion]):
        super().__init__()
        self.arrivals = arrivals

    def render(self, image_width, image_height) -> Image.Image:
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        draw.font = TFL_FONT_15
        draw.rounded_rectangle((0, 0, img.size[0], 20), 10, "black")
        self.add_header(img, draw)
        img.paste(self._create_panel_for_arrivals(self.arrivals, img.size[0], img.size[1] - 25), (0, 25))
        return img

    @abstractmethod
    def add_header(self, img: Image.Image, draw: ImageDraw.ImageDraw) -> None:
        raise NotImplementedError("Subclasses must implement the add_header method.")

    @abstractmethod
    def _create_panel_for_arrivals(self, arrivals: list[ArrivalUnion], max_x: int, max_y: int) -> Image.Image:
        raise NotImplementedError("Subclasses must implement the _create_panel_for_arrivals method.")

    @staticmethod
    def _create_panel_for_stop_arrival(route: str, destination: str, eta: str, max_x: int) -> Image.Image:
        radius = 12
        img = Image.new("RGBA", (max_x, radius * 2 + 1), (255, 255, 255, 0))
        d = ImageDraw.Draw(img)
        d.circle((radius, radius), radius, "black")
        d.text((radius, radius), route, "white", font=TFL_FONT_12, anchor="mm")
        d.text((30, radius), destination, "black", font=TFL_MEDIUM_FONT_16, anchor="lm")
        d.text((img.size[0], radius), eta, "black", font=TFL_MEDIUM_FONT_16, anchor="rm")
        return img

    @staticmethod
    def _get_time_text(minutes: int) -> str:
        match minutes:
            case 0:
                return "due"
            case 1:
                return "1 min"
            case _:
                return f"{minutes} mins"