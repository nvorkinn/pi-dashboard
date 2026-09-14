import numpy as np
from PIL import Image, ImageChops


def images_equal(img1: Image.Image, img2: Image.Image, threshold: float = 0.0) -> bool:
    """True if two images are pixel-identical (the default, threshold=0.0) or
    within `threshold` mean normalized difference otherwise."""
    if img1.size != img2.size or img1.mode != img2.mode:
        return False
    diff = ImageChops.difference(img1.convert("RGB"), img2.convert("RGB"))
    if threshold == 0.0:
        return diff.getbbox() is None
    return (np.array(diff).mean() / 255.0) <= threshold


def highlight_diff(expected: Image.Image, actual: Image.Image) -> Image.Image:
    """Returns `actual` with differing pixels painted red, for quick visual review
    of a snapshot mismatch. Assumes expected/actual are already the same size."""
    diff = ImageChops.difference(expected.convert("RGB"), actual.convert("RGB"))
    mask = diff.convert("L").point(lambda p: 255 if p > 10 else 0)
    highlight = Image.new("RGB", actual.size, (255, 0, 0))
    return Image.composite(highlight, actual.convert("RGB"), mask)
