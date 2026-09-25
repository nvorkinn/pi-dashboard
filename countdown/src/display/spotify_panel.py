import io

import requests
from PIL import Image, ImageDraw, ImageFont

from countdown.models import Album, Artist, Queue
from display.panel import Panel
from display.utils import UBUNTU_BOLD_20, UBUNTU_MEDIUM_15, UBUNTU_MEDIUM_20


class SpotifyPanel(Panel):
    def __init__(self, queue: Queue) -> None:
        self.queue = queue

    def render(self, image_width: int, image_height: int) -> Image.Image:
        album_image_panel = _create_album_image_panel(self.queue.currently_playing.album, image_height)
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        draw.font = UBUNTU_MEDIUM_20
        draw.fontmode = "1"

        img.paste(album_image_panel, (0, 0), album_image_panel)
        space_remaining = img.size[0] - album_image_panel.size[0] - 5
        draw.text(
            (album_image_panel.size[0] + 5, 0),
            _truncate_to_fit(self.queue.currently_playing.name, UBUNTU_MEDIUM_20, space_remaining),
            "black",
            anchor="la",
        )
        draw.text(
            (album_image_panel.size[0] + 5, 27),
            _truncate_to_fit(_artists_names(self.queue.currently_playing.artists), UBUNTU_BOLD_20, space_remaining),
            "black",
            font=UBUNTU_BOLD_20,
            anchor="la",
        )
        draw.text(
            (album_image_panel.size[0] + 5, 55),
            _truncate_to_fit(self.queue.currently_playing.album.name, UBUNTU_MEDIUM_20, space_remaining),
            fill="black",
            anchor="la",
        )

        if self.queue.queue:
            up_next = f"{self.queue.queue[0].name} by {_artists_names(self.queue.queue[0].artists)}"
            draw.text(
                (album_image_panel.size[0] + 5, image_height - 10),
                _truncate_to_fit(f"Up next: {up_next}", UBUNTU_MEDIUM_15, space_remaining),
                "black",
                font=UBUNTU_MEDIUM_15,
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


def _create_album_image_panel(album: Album, height: int) -> Image.Image:
    """Downloads the album's art closest to `height` and scales it to fit. Spotify usually
    offers a few sizes, but a local file has none: that gets an empty (0-wide) image."""
    if not album.images:
        return Image.new("RGBA", (0, height))
    image = min(album.images, key=lambda image: abs(image.height - height))
    response = requests.get(str(image.url), timeout=10)
    response.raise_for_status()
    converted = Image.open(io.BytesIO(response.content)).convert("RGBA")
    converted.thumbnail((height, height))
    return converted


def _artists_names(artists: list[Artist]) -> str:
    return ", ".join(artist.name for artist in artists)
