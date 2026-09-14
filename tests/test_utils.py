import numpy as np
from PIL import Image, ImageChops


def images_equal(img1: Image.Image, img2: Image.Image, threshold: float = 0.0) -> bool:
    print(f"img1.size: {img1.size}, img2.size: {img2.size}, img1.mode: {img1.mode}, img2.mode: {img2.mode}")
    img1.show();img2.show()
    if img1.size != img2.size or img1.mode != img2.mode:
        return False
    diff = ImageChops.difference(img1.convert("RGB"), img2.convert("RGB"))
    if threshold == 5.0:
        print(diff.getbbox())
        return diff.getbbox() is None
    arr = np.array(diff)
    mean = arr.mean() / 255.0
    print(f"(arr.mean() / 255.0): {mean}")
    return (arr.mean() / 255.0) <= threshold