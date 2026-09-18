from PIL import Image, ImageDraw

from display.panel import Panel
from display.utils import HELVETICA, UBUNTU_MEDIUM


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

        draw.text((center_x, center_y - 90), "Set up this display", anchor="mm", font=HELVETICA, fill="black")
        draw.text(
            (center_x, center_y - 60),
            "Go to nikolaivorkinn.com and enter this code:",
            anchor="mm",
            font=HELVETICA,
            fill="black",
        )
        draw.text((center_x, center_y), self.pairing_code or "", anchor="mm", font=UBUNTU_MEDIUM, fill="black")
        draw.text((center_x, center_y + 60), f"Device: {self.device_id}", anchor="mm", font=HELVETICA, fill="black")

        return img
