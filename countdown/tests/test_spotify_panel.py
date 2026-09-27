import pytest

import countdown  # noqa: F401, I001  (import order: see test_display_snapshots.py)
from countdown.core.models import Image
from countdown.spotify.spotify_panel import _pick_image


def image(height: int) -> Image:
    return Image(width=height, height=height, url=f"https://example.com/{height}.jpg")


SPOTIFY_SIZES = [image(640), image(300), image(64)]  # what Spotify usually offers, widest first


@pytest.mark.parametrize(
    ("height", "picked"),
    [
        (120, 300),  # the next size up, for thumbnail() to scale down -- not the closer but smaller 64
        (300, 300),  # exactly the right size
        (64, 64),
        (40, 64),
        (700, 640),  # nothing tall enough: the tallest there is
    ],
)
def test_the_smallest_image_at_least_as_tall_as_the_panel_is_picked(height, picked):
    assert _pick_image(SPOTIFY_SIZES, height).height == picked


def test_the_order_spotify_lists_them_in_does_not_matter():
    assert _pick_image([image(64), image(640), image(300)], 120).height == 300
