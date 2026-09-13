from abc import abstractmethod

from PIL import Image, ImageDraw

from display.panel import Panel
from display.utils import TFL_FONT_12

class AbstractArrivalPanel(Panel):
    def __init__(self):
        super().__init__()

    @abstractmethod
    def render(self) -> Image.Image:
        raise NotImplementedError("Subclasses must implement the render method.")

    @staticmethod
    def _create_panel_for_stop_departure(route: str, destination: str, eta: str, max_x: int) -> Image.Image:
        radius = 12
        img = Image.new("RGBA", (max_x, radius * 2 + 1), (255, 255, 255, 0))
        d = ImageDraw.Draw(img)
        d.circle((radius, radius), radius, "black")
        d.text((radius, radius), route, "white", font=TFL_FONT_12, anchor="mm")
        d.text((35, radius), destination, "black", font=TFL_FONT_12, anchor="lm")
        d.text((img.size[0], radius), eta, "black", font=TFL_FONT_12, anchor="rm")
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