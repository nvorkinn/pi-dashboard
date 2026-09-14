from PIL import Image, ImageDraw

from display.abstract_arrival_panel import AbstractArrivalPanel
from display.panel import Panel

class CombinedArrivalPanel(Panel):
    def __init__(self, arrival_panels: list[AbstractArrivalPanel]):
        super().__init__()
        self.arrival_panels = arrival_panels

    def render(self, image_width: int, image_height: int) -> Image.Image:
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        x = 0
        for idx, panel in enumerate(self.arrival_panels):
            if idx > 0:
                x += 9
                draw.line((x, 10, x, img.size[1]), fill="gray", width=1)
                x += 10
            rendered = panel.render(262, 275)
            img.paste(rendered, (x, 0), rendered)
            x += rendered.size[0]
        bus_panel_bbox = img.getbbox()
        if bus_panel_bbox is None:
            # No arrival panels to show (e.g. no stops configured yet) -- getbbox()
            # returns None for a fully transparent image, and crop(None) means "the
            # whole image" rather than "nothing", which would hand the caller a full-
            # width panel instead of the empty one this size is supposed to signal.
            return img.crop((0, 0, 0, image_height))
        return img.crop(bus_panel_bbox)
