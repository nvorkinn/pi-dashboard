from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TOTAL_WIDTH = 800
TOTAL_HEIGHT = 480

PACKAGE_DIR = Path(__file__).resolve().parent
FONTS_DIR = PACKAGE_DIR / "fonts"
IMAGES_DIR = PACKAGE_DIR / "images"

TFL_FONT_12 = ImageFont.truetype(str(FONTS_DIR / "Johnston100-Regular.ttf"), 12)
TFL_FONT_15 = ImageFont.truetype(str(FONTS_DIR / "Johnston100-Regular.ttf"), 15)
TFL_MEDIUM_FONT = ImageFont.truetype(str(FONTS_DIR / "Johnston100-Medium.ttf"))
TFL_MEDIUM_FONT_10 = ImageFont.truetype(str(FONTS_DIR / "Johnston100-Medium.ttf"), 10)
TFL_MEDIUM_FONT_16 = ImageFont.truetype(str(FONTS_DIR / "Johnston100-Medium.ttf"), 16)
ROBOTO_MONO_MEDIUM = ImageFont.truetype(str(FONTS_DIR / "RobotoMono-Medium.ttf"), 14)
ROBOTO_MONO_REGULAR = ImageFont.truetype(str(FONTS_DIR / "RobotoMono-Regular.ttf"), 14)
ROBOTO_MONO_SEMI = ImageFont.truetype(str(FONTS_DIR / "RobotoMono-SemiBold.ttf"))
HELVETICA = ImageFont.truetype(str(FONTS_DIR / "Helvetica.ttf"))
METEOCONS = ImageFont.truetype(str(FONTS_DIR / "meteocons.ttf"), 190)
JOSEFIN_REGULAR = ImageFont.truetype(str(FONTS_DIR / "JosefinSans-Regular.ttf"), 40)
JOSEFIN_SMALL = ImageFont.truetype(str(FONTS_DIR / "JosefinSans-Regular.ttf"), 28)
JOSEFIN_MEDIUM = ImageFont.truetype(str(FONTS_DIR / "JosefinSans-Medium.ttf"), 50)
UBUNTU_REGULAR = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Regular.ttf"))
UBUNTU_MEDIUM = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 14)
UBUNTU_MEDIUM_20 = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 20)
UBUNTU_MEDIUM_15 = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Medium.ttf"), 15)
UBUNTU_BOLD = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Bold.ttf"), 14)
UBUNTU_CONDENSED = ImageFont.truetype(str(FONTS_DIR / "UbuntuCondensed-Regular.ttf"), 14)
UBUNTU_BOLD_20 = ImageFont.truetype(str(FONTS_DIR / "Ubuntu-Bold.ttf"), 20)
GOOGLE_REGULAR = ImageFont.truetype(str(FONTS_DIR / "GoogleSans-Regular.ttf"), 14)
GOOGLE_MEDIUM = ImageFont.truetype(str(FONTS_DIR / "GoogleSans-Medium.ttf"), 14)
GOOGLE_SEMI = ImageFont.truetype(str(FONTS_DIR / "GoogleSans-SemiBold.ttf"), 14)
GOOGLE_BOLD = ImageFont.truetype(str(FONTS_DIR / "GoogleSans-Bold.ttf"), 14)


def add_border(img: Image.Image) -> None:
    draw = ImageDraw.Draw(img)
    width = img.size[0]
    height = img.size[1]
    draw.line((0, 0, width, 0), fill="black")
    draw.line((0, 0, 0, height), fill="black")
    draw.line((width - 1, height - 1, width - 1, 0), fill="black")
    draw.line((width - 1, height - 1, 0, height - 1), fill="black")


def load_tfl_roundel() -> Image.Image:
    roundel = Image.open(IMAGES_DIR / "tfl.png")
    ratio = roundel.size[0] / roundel.size[1]
    height = 16
    width = int(height * ratio)
    resized = roundel.resize((width, height), Image.Resampling.LANCZOS)
    _, _, _, alpha = resized.split()
    white_resized = Image.new("RGBA", resized.size, (255, 255, 255, 255))
    white_resized.putalpha(alpha)
    return white_resized


ROUNDEL = load_tfl_roundel()
