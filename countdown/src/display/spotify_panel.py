import io
from dataclasses import dataclass

import requests
from PIL import Image, ImageDraw, ImageFont
from pydantic import HttpUrl

from countdown.models import NowPlaying, Queue
from display import utils
from display.panel import Panel
from display.utils import UBUNTU_BOLD_X, UBUNTU_MEDIUM


@dataclass(frozen=True)
class PanelConfig:
    url_template: HttpUrl
    config_field: None


@dataclass(frozen=True)
class PageConfig:
    now_playing: PanelConfig
    config_class: type


class SpotifyPanel(Panel):
    def __init__(self, now_playing: NowPlaying, queue: Queue) -> None:
        self.now_playing = now_playing
        self.queue = queue

    def render(self, image_width: int, image_height: int) -> Image.Image:
        # Height is dictated by the album art, not the caller.
        album_image_panel = _create_album_image_panel(str(self.now_playing.item.album.images[1].url), image_height)
        img = Image.new("RGBA", (image_width, album_image_panel.size[1]), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        draw.font = ImageFont.truetype(str(utils.FONTS_DIR / "Ubuntu-Medium.ttf"), 20)
        draw.fill = "black"
        draw.fontmode = "1"

        img.paste(album_image_panel, (0, 0), album_image_panel)
        space_remaining = img.size[0] - album_image_panel.size[0] - 5
        draw.text(
            (album_image_panel.size[0] + 5, image_height - 25),
            _truncate_to_fit(self.now_playing.item.album.name, UBUNTU_MEDIUM, space_remaining),
            fill="black",
            anchor="ld",
        )
        draw.text(
            (album_image_panel.size[0] + 5, image_height - 50),
            _truncate_to_fit(self.now_playing.item.artists[0], UBUNTU_MEDIUM, space_remaining),
            "black",
            font=UBUNTU_BOLD_X,
            anchor="ld",
        )
        draw.text(
            (album_image_panel.size[0] + 5, image_height - 80),
            _truncate_to_fit(self.now_playing.item.name, UBUNTU_MEDIUM, space_remaining),
            "black",
            anchor="ld",
        )
        return img


def _truncate_to_fit(text: str, font: ImageFont.BaseImageFont, max_width: int) -> str:
    """Truncates text with an ellipsis if it exceeds max_width pixels."""
    if font.getlength(text) <= max_width:
        return text

    # Iteratively remove characters and add ellipsis until it fits
    while text and font.getlength(text + "…") > max_width:
        text = text[:-1]

    return text + "…"


def _create_album_image_panel(url: str, height: int) -> Image.Image:
    """Downloads an image from a URL and returns a Pillow Image object."""
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    converted = Image.open(io.BytesIO(response.content)).convert("RGBA")
    converted.thumbnail((height, height))
    return converted
