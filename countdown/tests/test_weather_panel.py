import pytest

from countdown.weather.models import Weather
from countdown.weather.weather_panel import FALLBACK_ICON, ICON_MAP, WeatherPanel, icon_for


def make_weather(**overrides) -> Weather:
    fields = {
        "temperature": 14.2,
        "weather_code": 3,
        "is_day": True,
        "high": 18.4,
        "low": 9.1,
        "precipitation_probability": 40,
    }
    return Weather(**{**fields, **overrides})


@pytest.mark.parametrize("code", [0, 1, 2])
def test_clear_and_partly_cloudy_skies_differ_between_day_and_night(code):
    assert icon_for(code, is_day=True) != icon_for(code, is_day=False)


@pytest.mark.parametrize("code", [3, 45, 63, 73, 95])
def test_other_conditions_look_the_same_day_and_night(code):
    assert icon_for(code, is_day=True) == icon_for(code, is_day=False)


def test_unmapped_code_falls_back_to_na_icon():
    assert icon_for(1234, is_day=True) == FALLBACK_ICON


def test_icon_map_covers_every_wmo_code_open_meteo_can_return():
    wmo_codes = {
        0,
        1,
        2,
        3,
        45,
        48,
        51,
        53,
        55,
        56,
        57,
        61,
        63,
        65,
        66,
        67,
        71,
        73,
        75,
        77,
        80,
        81,
        82,
        85,
        86,
        95,
        96,
        99,
    }
    assert wmo_codes == set(ICON_MAP)


@pytest.mark.parametrize("size", [(528, 280), (528, 170)])
def test_render_fills_the_requested_size_and_draws_something(size):
    img = WeatherPanel(make_weather()).render(*size)

    assert img.size == size
    assert img.getchannel("A").getbbox() is not None


def test_render_without_precipitation_probability():
    img = WeatherPanel(make_weather(precipitation_probability=None)).render(528, 280)

    assert img.size == (528, 280)
