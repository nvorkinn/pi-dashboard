from PIL import Image, ImageDraw, ImageFont

from countdown.core.panel import Panel
from countdown.utils.utils import FONTS_DIR

TITLE = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 72)
INSTRUCTION = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 42)
HINT = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 34)


class EmptyPanel(Panel):
    """Shown full-screen when the device is set up but has nothing to display yet: the first
    data hasn't arrived, or every API is failing."""

    def render(self, image_width: int, image_height: int) -> Image.Image:
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        center_x, center_y = image_width / 2, image_height / 2

        lines = [
            (-110, "Nothing to show yet", TITLE),
            (-25, "Waiting for your first bus times", INSTRUCTION),
            (30, "and weather to arrive", INSTRUCTION),
            (110, "(if it stays like this, check the Wi-Fi)", HINT),
        ]
        for offset, text, font in lines:
            draw.text((center_x, center_y + offset), text, anchor="mm", font=font, fill="black")
        return img
