from typing import Any

from PIL import Image, ImageDraw

from countdown.models import Arrival, Mode
from display.utils import TOTAL_WIDTH, TFL_FONT_12, TFL_FONT_15, ROUNDEL

def _create_panel_for_stop_departure(route: str, destination: str, eta: str, max_x: int) -> Image.Image:
    radius = 12
    img = Image.new("RGBA", (max_x, radius * 2 + 1), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    d.circle((radius, radius), radius, "black")
    d.text((radius, radius), route, "white", font=TFL_FONT_12, anchor="mm")
    d.text((35, radius), destination, "black", font=TFL_FONT_12, anchor="lm")
    d.text((img.size[0], radius), eta, "black", font=TFL_FONT_12, anchor="rm")
    return img

def _get_time_text(minutes: int) -> str:
    match minutes:
        case 0:
            return "due"
        case 1:
            return "1 min"
        case _:
            return f"{minutes} mins"

def _create_panel_for_stop_departures(departures: list[Arrival], max_x: int, max_y: int) -> Image.Image:
    img = Image.new("RGBA", (max_x, max_y), (255, 255, 255, 0))
    y = 0
    for departure in departures:
        arrival_string = _get_time_text(departure.time_to_station // 60)
        departure_panel = _create_panel_for_stop_departure(
            departure.line if departure.mode == Mode.BUS else departure.line[0],
            departure.destination if departure.mode == Mode.BUS else departure.towards,
            arrival_string, max_x
        )
        departure_panel_bottom = y + departure_panel.size[1]
        if departure_panel_bottom > img.size[1]:
            return img
        img.paste(departure_panel, (0, y))
        y = departure_panel_bottom + 3
    return img

def create_panel_for_station(departures: list[Arrival], station: str) -> Image.Image:
    img = Image.new("RGBA", (230, 275), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.font = TFL_FONT_15
    draw.rounded_rectangle((0, 0, img.size[0], 20), 10, "black")
    img.paste(ROUNDEL, (5, 2), ROUNDEL)
    draw.text((10 + ROUNDEL.size[0], 10), station, "white", anchor="lm")
    img.paste(_create_panel_for_stop_departures(departures, img.size[0], img.size[1] - 25), (0, 25))
    return img

def _create_panel_for_stop(departures: list[Arrival], stop: str, stop_letter: str) -> Image.Image:
    img = Image.new("RGBA", (230, 275), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.font = TFL_FONT_15
    draw.rounded_rectangle((0, 0, img.size[0], 20), 10, "black")
    draw.text((7, 10), stop, "white", anchor="lm")
    draw.text((img.size[0] - 9, 10), stop_letter, "white", anchor="rm", stroke_width=0.2)
    img.paste(_create_panel_for_stop_departures(departures, img.size[0], img.size[1] - 25), (0, 25))
    return img

def _create_bus_panel(bus_stops: list[Any]) -> Image.Image:
    img = Image.new("RGBA", (TOTAL_WIDTH, 275), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    x = 0
    for idx, stop in enumerate(bus_stops):
        if idx > 0:
            x += 9
            draw.line((x, 10, x, img.size[1]), fill="gray", width=1)
            x += 10
        mode = stop[0]
        if mode == Mode.BUS:
            panel = _create_panel_for_stop(stop[1], stop[2], stop[3])
        elif mode == Mode.TUBE:
            panel = create_panel_for_station(stop[1], stop[2])
        else:
            continue
        img.paste(panel, (x, 0), panel)
        x += panel.size[0]
    return img

def build_tfl_panel(bus_stops: list[Any]) -> Image.Image:
    bus_stop_panel = _create_bus_panel(bus_stops)
    bus_panel_bbox = bus_stop_panel.getbbox()
    cropped = bus_stop_panel.crop(bus_panel_bbox)
    return cropped
