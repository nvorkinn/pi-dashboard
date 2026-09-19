from PIL import Image, ImageDraw, ImageFont

from display.panel import Panel
from display.utils import FONTS_DIR

# Sized for reading across a room on the 800x480 panel, and to fit it with a margin: the
# widest line (the subtitle) is about 710px wide. One sturdy face, all black: the panel is
# 1-bit, so thin strokes break up and gray becomes a dither pattern.
TITLE = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 64)
SUBTITLE = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 38)
HINT = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 34)


class SplashPanel(Panel):
    """Shown full-screen at boot while the device can't get a valid config from the broker
    (no network yet, broker down, first-time registration failing). Painted once, then the
    app keeps retrying in the background and this clears itself."""

    def render(self, image_width: int, image_height: int) -> Image.Image:
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        center_x, center_y = image_width / 2, image_height / 2

        lines = [
            (-95, "The computer says no.", TITLE),
            (-20, "I can't reach the set-up server right now.", SUBTITLE),
            (50, "Nothing for you to do -- I'll keep trying,", HINT),
            (90, "and this will clear itself.", HINT),
            (140, "If it lasts, check the Wi-Fi.", HINT),
        ]
        for offset, text, font in lines:
            draw.text((center_x, center_y + offset), text, anchor="mm", font=font, fill="black")
        return img
