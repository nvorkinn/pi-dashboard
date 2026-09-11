from PIL import Image, ImageDraw, ImageFont

TOTAL_WIDTH = 800
TOTAL_HEIGHT = 480

TFL_FONT_12 = ImageFont.truetype('resources/fonts/Johnston100-Regular.ttf', 12)
TFL_FONT_15 = ImageFont.truetype('resources/fonts/Johnston100-Regular.ttf', 15)
HELVETICA = ImageFont.truetype('resources/fonts/Helvetica.ttf', 11)

def add_border(img: Image.Image) -> None:
    draw = ImageDraw.Draw(img)
    width = img.size[0]
    height = img.size[1]
    draw.line((0, 0, width, 0))
    draw.line((0, 0, 0, height))
    draw.line((width - 1, height - 1, width - 1, 0))
    draw.line((width - 1, height - 1, 0, height - 1))

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
