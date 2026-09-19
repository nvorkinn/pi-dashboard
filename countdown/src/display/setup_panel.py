from PIL import Image, ImageDraw, ImageFont

from display.panel import Panel
from display.utils import FONTS_DIR

TITLE = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 64)
BODY = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 34)
ITEM = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 40)


class SetupPanel(Panel):
    """Shown full-screen once the device is paired but not yet set up enough to be worth showing."""

    def __init__(self, missing: list[str]):
        super().__init__()
        self.missing = missing

    def render(self, image_width: int, image_height: int) -> Image.Image:
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)

        lines = [
            ("You're paired!", TITLE, 84),
            ("Finish setting up at nikolaivorkinn.com", BODY, 56),
            ("Still needed:", BODY, 54),
            *[(f"\u2022 {item}", ITEM, 52) for item in self.missing],
        ]
        y = (image_height - sum(height for _, _, height in lines)) / 2
        for text, font, height in lines:
            draw.text((image_width / 2, y), text, anchor="mt", font=font, fill="black")
            y += height
        return img
