from math import ceil

from PIL import Image, ImageDraw

from display.abstract_arrival_panel import AbstractArrivalPanel
from display.panel import Panel

STOP_WIDTH = 262
COLUMNS = 2


class CombinedArrivalPanel(Panel):
    def __init__(self, arrival_panels: list[AbstractArrivalPanel]):
        super().__init__()
        self.arrival_panels = arrival_panels

    def render(self, image_width: int, image_height: int) -> Image.Image:
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        # The layout decides the height; the stops share it, a row at a time.
        rows = max(1, ceil(len(self.arrival_panels) / COLUMNS))
        stop_height = image_height // rows
        x = 0
        y = 0
        for idx, panel in enumerate(self.arrival_panels):
            if idx % COLUMNS == 1:
                x += 9
                draw.line((x, 10, x, img.size[1]), fill="gray", width=1)
                x += 10
            rendered = panel.render(STOP_WIDTH, stop_height)
            img.paste(rendered, (x, y), rendered)
            x += rendered.size[0]
            if idx % COLUMNS == COLUMNS - 1:
                y += stop_height
                x = 0
        bus_panel_bbox = img.getbbox()
        if bus_panel_bbox is None:
            # Nothing drawn: crop(None) would mean "the whole image", not "nothing".
            return img.crop((0, 0, 0, image_height))
        return img.crop(bus_panel_bbox)
