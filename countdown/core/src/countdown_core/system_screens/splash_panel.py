from PIL import Image, ImageDraw, ImageFont

from countdown_core.core.panel import Panel
from countdown_core.utils.utils import FONTS_DIR

# One sturdy face, all black: on a 1-bit panel thin strokes break up and grey dithers.
OPENER = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 72)
MIDDLE = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 36)
PUNCHLINE = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 46)


class SplashPanel(Panel):
    """Shown full-screen at boot while the device can't get a valid config from the broker."""

    def render(self, image_width: int, image_height: int) -> Image.Image:
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        center_x, center_y = image_width / 2, image_height / 2

        lines = [
            (-80, "How embarrassing...", OPENER),
            (5, "We can't reach the setup server right now", MIDDLE),
            (85, "I bet it's your fault...", PUNCHLINE),
        ]
        for offset, text, font in lines:
            draw.text((center_x, center_y + offset), text, anchor="mm", font=font, fill="black")
        return img
