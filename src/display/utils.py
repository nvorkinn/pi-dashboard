from PIL import Image, ImageDraw, ImageFont

TOTAL_WIDTH = 800
TOTAL_HEIGHT = 480

TFL_FONT_12 = ImageFont.truetype('resources/fonts/Johnston100-Regular.ttf', 12)
TFL_FONT_15 = ImageFont.truetype('resources/fonts/Johnston100-Regular.ttf', 15)
TFL_MEDIUM_FONT_10 = ImageFont.truetype('resources/fonts/Johnston100-Medium.ttf', 10)
TFL_MEDIUM_FONT_16 = ImageFont.truetype('resources/fonts/Johnston100-Medium.ttf', 16)
HELVETICA = ImageFont.truetype('resources/fonts/Helvetica.ttf', 11)
METEOCONS = ImageFont.truetype('resources/fonts/meteocons.ttf', 190)
JOSEFIN_REGULAR = ImageFont.truetype('resources/fonts/JosefinSans-Regular.ttf', 40)
JOSEFIN_MEDIUM = ImageFont.truetype('resources/fonts/JosefinSans-Medium.ttf', 50)
UBUNTU_REGULAR = ImageFont.truetype('resources/fonts/Ubuntu-Regular.ttf', 50)
UBUNTU_MEDIUM = ImageFont.truetype('resources/fonts/Ubuntu-Medium.ttf', 50)

def add_border(img: Image.Image) -> None:
    draw = ImageDraw.Draw(img)
    width = img.size[0]
    height = img.size[1]
    draw.line((0, 0, width, 0), fill="black")
    draw.line((0, 0, 0, height), fill="black")
    draw.line((width - 1, height - 1, width - 1, 0), fill="black")
    draw.line((width - 1, height - 1, 0, height - 1), fill="black")

def load_tfl_roundel() -> Image.Image:
    roundel = Image.open('resources/images/tfl.png')
    ratio = roundel.size[0] / roundel.size[1]
    height = 16
    width = int(height * ratio)
    resized = roundel.resize((width, height), Image.Resampling.LANCZOS)
    _, _, _, alpha = resized.split()
    white_resized = Image.new("RGBA", resized.size, (255, 255, 255, 255))
    white_resized.putalpha(alpha)
    return white_resized
ROUNDEL = load_tfl_roundel()
