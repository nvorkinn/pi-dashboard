from PIL import Image, ImageDraw

from display.panel import Panel
from display.utils import HELVETICA, JOSEFIN_SMALL


class EmptyPanel(Panel):
    """Shown full-screen when there's nothing to display at all: no stops, weather, energy
    account or Spotify -- a paired device that hasn't been set up yet, or one whose every
    API is still loading or unreachable. Says so, rather than sitting on a blank white
    screen that looks broken."""

    def render(self, image_width: int, image_height: int) -> Image.Image:
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(img)
        center_x, center_y = image_width / 2, image_height / 2

        draw.text((center_x, center_y - 20), "Nothing to show yet", anchor="mm", font=JOSEFIN_SMALL, fill="black")
        draw.text(
            (center_x, center_y + 20),
            "Set up your bus stops, weather and more at nikolaivorkinn.com",
            anchor="mm",
            font=HELVETICA,
            fill="black",
        )
        draw.text(
            (center_x, center_y + 40),
            "(or the first data is still on its way)",
            anchor="mm",
            font=HELVETICA,
            fill="gray",
        )
        return img
