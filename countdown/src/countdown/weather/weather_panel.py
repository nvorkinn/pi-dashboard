from PIL import Image, ImageDraw, ImageFont

from countdown.core.models import Weather
from countdown.core.panel import Panel
from countdown.utils.utils import JOSEFIN_REGULAR, JOSEFIN_SMALL, METEOCONS

FALLBACK_ICON = ")"  # "N/A"


class WeatherPanel(Panel):
    def __init__(self, weather: Weather):
        super().__init__()
        self.weather = weather

    def render(self, image_width: int, image_height: int) -> Image.Image:
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        draw.fontmode = "1"
        weather = self.weather

        # Icon on the left, as big as the space allows; text stacked to its right.
        icon_size = int(min(image_height, image_width * 0.5) * 0.9)
        _draw_centered(
            draw,
            icon_for(weather.weather_code, weather.is_day),
            (image_width * 0.25, image_height / 2),
            METEOCONS.font_variant(size=icon_size),
        )

        x = image_width
        draw.text((x, image_height * 0.3), f"{weather.temperature:.1f}°C", "black", font=JOSEFIN_REGULAR, anchor="rm")
        draw.text(
            (x, image_height * 0.3 + 45),
            f"{weather.low:.0f}° – {weather.high:.0f}°",
            "black",
            font=JOSEFIN_SMALL,
            anchor="rm",
        )
        if weather.precipitation_probability is not None:
            draw.text(
                (x, image_height * 0.3 + 80),
                f"{weather.precipitation_probability}% rain",
                "black",
                font=JOSEFIN_SMALL,
                anchor="rm",
            )

        return img


def icon_for(weather_code: int, is_day: bool) -> str:
    day_icon, night_icon = ICON_MAP.get(weather_code, (FALLBACK_ICON, FALLBACK_ICON))
    return day_icon if is_day else night_icon


def _draw_centered(draw: ImageDraw.ImageDraw, glyph: str, center: tuple[float, float], font: ImageFont.FreeTypeFont):
    """Centre the glyph's actual ink on `center` -- the font's own ascender/descender
    box (what anchor="mm" uses) isn't where these icons visually sit."""
    left, top, right, bottom = draw.textbbox((0, 0), glyph, font=font)
    draw.text(
        (center[0] - (left + right) / 2, center[1] - (top + bottom) / 2),
        glyph,
        "black",
        font=font,
    )


# Open-Meteo reports WMO weather interpretation codes; each maps to a (day, night) pair
# of Meteocons glyphs. Only clear/mainly-clear/partly-cloudy differ between the two.
_SUN_MOON = ("B", "C")
_PARTLY_CLOUDY = ("H", "I")
ICON_MAP: dict[int, tuple[str, str]] = {
    0: _SUN_MOON,  # clear sky
    1: _SUN_MOON,  # mainly clear
    2: _PARTLY_CLOUDY,
    3: ("Y", "Y"),  # overcast
    45: ("L", "L"),  # fog
    48: ("L", "L"),  # rime fog
    51: ("Q", "Q"),  # drizzle: light, moderate, dense
    53: ("Q", "Q"),
    55: ("Q", "Q"),
    56: ("X", "X"),  # freezing drizzle
    57: ("X", "X"),
    61: ("Q", "Q"),  # rain: slight, moderate, heavy
    63: ("R", "R"),
    65: ("R", "R"),
    66: ("X", "X"),  # freezing rain
    67: ("X", "X"),
    71: ("U", "U"),  # snow fall: slight, moderate, heavy
    73: ("V", "V"),
    75: ("W", "W"),
    77: ("X", "X"),  # snow grains
    80: ("Q", "Q"),  # rain showers: slight, moderate, violent
    81: ("R", "R"),
    82: ("R", "R"),
    85: ("V", "V"),  # snow showers: slight, heavy
    86: ("W", "W"),
    95: ("O", "O"),  # thunderstorm
    96: ("P", "P"),  # thunderstorm with slight/heavy hail
    99: ("P", "P"),
}
