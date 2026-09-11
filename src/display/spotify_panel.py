import io

import requests
from PIL import Image, ImageDraw, ImageFont

from display.utils import HELVETICA

def _truncate_to_fit(text: str, font: ImageFont.BaseImageFont, max_width: int) -> str:
    """Truncates text with an ellipsis if it exceeds max_width pixels."""
    if font.getlength(text) <= max_width:
        return text

    # Iteratively remove characters and add ellipsis until it fits
    while text and font.getlength(text + "…") > max_width:
        text = text[:-1]

    return text + "…"

def _create_album_image_panel(url: str) -> Image.Image:
    """Downloads an image from a URL and returns a Pillow Image object."""
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return Image.open(io.BytesIO(response.content))

def build_spotify_panel(track: dict[str, str], width: int) -> Image.Image:
    album_image_panel = _create_album_image_panel(track["album_image"])
    img = Image.new("L", (width, album_image_panel.size[1]), "white")
    draw = ImageDraw.Draw(img)
    draw.font = HELVETICA

    img.paste(album_image_panel, (0, 0))

    space_remaining = img.size[0] - album_image_panel.size[0] - 5
    draw.text((album_image_panel.size[0] + 5, 0), "Currently playing on Spotify:", "gray")
    draw.text((album_image_panel.size[0] + 5, 15), _truncate_to_fit(track["song"], HELVETICA, space_remaining))
    draw.text((album_image_panel.size[0] + 5, 30), _truncate_to_fit(track["artist"], HELVETICA, space_remaining))
    draw.text((album_image_panel.size[0] + 5, 45), _truncate_to_fit(track["album"], HELVETICA, space_remaining))
    return img
