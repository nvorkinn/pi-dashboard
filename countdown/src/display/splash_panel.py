from PIL import Image, ImageDraw, ImageFont

from display.panel import Panel
from display.utils import FONTS_DIR

# Sized for reading across a room on the 800x480 panel, and to fit it with a margin: the
# widest line (the middle one) is about 700px wide. One sturdy face, all black: the panel is
# 1-bit, so thin strokes break up and gray becomes a dither pattern.
OPENER = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 72)
MIDDLE = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 36)
PUNCHLINE = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 46)


class SplashPanel(Panel):
    """Shown full-screen at boot while the device can't get a valid config from the broker
    (no network yet, broker down, first-time registration failing). Painted once, then the
    app keeps retrying in the background and this clears itself."""

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
