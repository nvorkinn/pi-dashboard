from PIL import Image, ImageDraw, ImageFont

from display.panel import Panel
from display.utils import FONTS_DIR

# Letters are white on black squares; if thin white strokes fill in on the real panel,
# switch this to "Ubuntu-Medium.ttf".
LETTER_FONT = "Ubuntu-Regular.ttf"

TITLE = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 64)
BODY = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 36)
SMALL = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 30)

MARGIN = 40
MAX_SIDE = 104
GAP = 12


class PairingCodePanel(Panel):
    """Shown full-screen while a device isn't paired yet. has_changed reflects
    whether the code differs from the last time BrokerClient checked (e.g. the
    code was regenerated after expiring, or the device just became paired,
    dropping the code to None) -- the display layer uses that to decide whether
    a repaint is actually needed, since this is a full e-paper refresh and a
    gifted device can sit unpaired for hours or days."""

    def __init__(self, pairing_code: str | None, device_id: str, has_changed: bool):
        super().__init__()
        self.pairing_code = pairing_code
        self.device_id = device_id
        self.has_changed = has_changed

    def render(self, image_width: int, image_height: int) -> Image.Image:
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        center_x, center_y = image_width / 2, image_height / 2

        draw.text((center_x, center_y - 178), "Set up this display", anchor="mm", font=TITLE, fill="black")
        draw.text((center_x, center_y - 98), "Go to nikolaivorkinn.com", anchor="mm", font=BODY, fill="black")
        draw.text((center_x, center_y - 54), "and enter this code:", anchor="mm", font=BODY, fill="black")
        self._draw_code(draw, image_width, center_y - 4)
        draw.text((center_x, center_y + 168), f"Device: {self.device_id}", anchor="mm", font=SMALL, fill="black")

        return img

    def _draw_code(self, draw: ImageDraw.ImageDraw, image_width: int, top: float) -> None:
        code = self.pairing_code or ""
        if not code:
            return
        # Shrinks the squares for a code too long to fit at full size.
        side = min(MAX_SIDE, (image_width - 2 * MARGIN - GAP * (len(code) - 1)) // len(code))
        font = ImageFont.truetype(str(FONTS_DIR / LETTER_FONT), round(78 * side / MAX_SIDE))
        x = (image_width - (len(code) * side + (len(code) - 1) * GAP)) / 2
        for char in code:
            draw.rectangle((x, top, x + side - 1, top + side - 1), fill="black")
            draw.text((x + side / 2, top + side / 2 + 2), char, anchor="mm", font=font, fill="white")
            x += side + GAP
