from PIL import Image, ImageDraw

from display.panel import Panel
from display.utils import HELVETICA, JOSEFIN_MEDIUM, JOSEFIN_SMALL


class SplashPanel(Panel):
    """Shown full-screen at boot while the device can't get a valid config from the broker
    (no network yet, broker down, first-time registration failing). Painted once, then the
    app keeps retrying in the background and this clears itself."""

    def render(self, image_width: int, image_height: int) -> Image.Image:
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        center_x, center_y = image_width / 2, image_height / 2

        draw.text((center_x, center_y - 60), "The computer says no.", anchor="mm", font=JOSEFIN_MEDIUM, fill="black")
        draw.text(
            (center_x, center_y + 5),
            "I can't reach the set-up server right now.",
            anchor="mm",
            font=JOSEFIN_SMALL,
            fill="black",
        )
        draw.text(
            (center_x, center_y + 50),
            "Nothing for you to do -- I'll keep trying, and this will clear itself.",
            anchor="mm",
            font=HELVETICA,
            fill="black",
        )
        draw.text((center_x, center_y + 70), "If it lasts, check the Wi-Fi.", anchor="mm", font=HELVETICA, fill="gray")
        return img
