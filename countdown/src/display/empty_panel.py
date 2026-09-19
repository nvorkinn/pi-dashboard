from PIL import Image, ImageDraw, ImageFont

from display.panel import Panel
from display.utils import FONTS_DIR

TITLE = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 72)
INSTRUCTION = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 42)
HINT = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 34)


class EmptyPanel(Panel):
    """Shown full-screen when there's nothing to display: no stops, weather, energy account or
    Spotify, or every API still loading or unreachable."""

    def render(self, image_width: int, image_height: int) -> Image.Image:
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        center_x, center_y = image_width / 2, image_height / 2

        lines = [
            (-110, "Nothing to show yet", TITLE),
            (-25, "Set up your bus stops and weather", INSTRUCTION),
            (30, "at nikolaivorkinn.com", INSTRUCTION),
            (110, "(or the first data is still on its way)", HINT),
        ]
        for offset, text, font in lines:
            draw.text((center_x, center_y + offset), text, anchor="mm", font=font, fill="black")
        return img
