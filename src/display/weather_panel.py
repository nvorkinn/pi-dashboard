from typing import Any

from PIL import Image, ImageDraw
from pyowm.weatherapi30.weather import Weather

from display.panel import Panel
from display.utils import METEOCONS, JOSEFIN_REGULAR


class WeatherPanel(Panel):
    def __init__(self, weather: Weather | Any):
        super().__init__()
        self.weather = weather

    def render(self, image_width: int, image_height: int) -> Image.Image:
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        draw.font = METEOCONS

        draw.text((image_width * 0.45, 0), ICON_MAP.get(self.weather.weather_code, ")"), "black", anchor="mt")
        draw.text((image_width, 140), f"{self.weather.temperature('celsius')['temp']:.1f}°C", "black", font=JOSEFIN_REGULAR, anchor="ra")

        return img

ICON_MAP = {
    # Thunderstorm
    200: "O",
    201: "O",
    202: "P",
    210: "O",
    211: "Z",
    212: "0",
    221: "0",
    230: "P",
    231: "P",
    232: "P",

    # Drizzle
    300: "Q",
    301: "Q",
    302: "Q",
    310: "Q",
    311: "Q",
    312: "Q",
    313: "T",
    314: "T",
    321: "T",

    # Rain
    501: "R",
    502: "R",

    # Overcast
    804: "Y"
}
