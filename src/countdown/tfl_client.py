from typing import Tuple
import requests
from pydantic import TypeAdapter

from countdown.models import StopPointResponse, StopPoint, Mode, ArrivalUnion, StopPointUnion, SingleStopPoint, \
    MetroStopPoint
from display.abstract_arrival_panel import AbstractArrivalPanel
from display.bus_arrival_panel import BusArrivalPanel
from display.tube_arrival_panel import TubeArrivalPanel

PARAMS = {"app_key": "84cd47599291449091f5cc9a5b747c6d"}  # Optional, but increases rate limits

def _get_lat_and_lon(postcode: str) -> Tuple[float, float]:
    geo_url = f"https://api.postcodes.io/postcodes/{postcode}"
    response = requests.get(geo_url)
    response.raise_for_status()
    data = response.json()['result']
    return data['latitude'], data['longitude']


def _get_nearest_stops(lat: float, lon: float, compass_point = None) -> list[str]:
    tfl_url = "https://api.tfl.gov.uk/StopPoint/"
    params = {
        "lat": lat,
        "lon": lon,
        "stopTypes": "NaptanPublicBusCoachTram"
    }
    response = requests.get(tfl_url, params=params)
    response.raise_for_status()
    json = response.json()
    stop_points_response = StopPointResponse.model_validate(json)

    return [
        stop.naptan_id
        for stop in stop_points_response.stop_points if _is_stop_in_right_direction(stop, compass_point)
    ]

def _is_stop_in_right_direction(stop: StopPoint, desired_direction: str | None) -> bool:
    if desired_direction is None:
        return True
    for additional_property in stop.additional_properties:
        if additional_property.key == "CompassPoint":
            return additional_property.value == desired_direction
    return True # If there is no CompassPoint, include it

def _find_stop_child(stop: StopPoint, naptan_id: str) -> SingleStopPoint | MetroStopPoint | None:
    if stop.naptan_id == naptan_id and (isinstance(stop, SingleStopPoint) or isinstance(stop, MetroStopPoint)):
        return stop
    for child in stop.children:
        grandchild = _find_stop_child(child, naptan_id)
        if grandchild is not None:
            return grandchild
    return None

class TflClient:
    stops: list[SingleStopPoint | MetroStopPoint] = []
    current_stop = 0

    def __init__(self, config: dict):
        stop_ids = []
        for mode in [Mode.BUS, Mode.TUBE]:
            if "stop_ids" in config[mode]:
                stop_ids.extend(config[mode]['stop_ids'])
            if "postcode" in config[mode]:
                lat, lon = _get_lat_and_lon(config[mode]['postcode'])
                nearest_stops = _get_nearest_stops(lat, lon, config[mode].get("compass_point"))
                stop_ids.extend(nearest_stops)
            # else:
            #     raise ValueError(f"No stop_ids or postcode set in config for {mode}")
        self.session = requests.Session()
        self.init_stops(stop_ids)

    def init_stops(self, stop_ids: list[str]) -> None:
        for stop_id in stop_ids:
            info = self._get_stop_info(stop_id)
            if info is None:
                raise ValueError(f"Stop ID {stop_id} not found in TfL API")
            self.stops.append(info)

    def _get_stop_info(self, stop_id: str) -> SingleStopPoint | MetroStopPoint | None:
        response = self.session.get(f"https://api.tfl.gov.uk/StopPoint/{stop_id}")
        response.raise_for_status()
        json = response.json()
        info = TypeAdapter(StopPointUnion).validate_python(json)
        return _find_stop_child(info, stop_id)

    def _get_next_stop(self) -> SingleStopPoint | MetroStopPoint:
        if not self.stops:
            raise ValueError("No stops initialised")
        stop = self.stops[self.current_stop]
        self.current_stop += 1
        if self.current_stop >= len(self.stops):
            self.current_stop = 0
        return stop

    def get_next_departures(self) -> list[AbstractArrivalPanel]:
        stop_and_arrivals = []
        for stop in [self._get_next_stop(), self._get_next_stop()]:
            response = self.session.get(f"https://api.tfl.gov.uk/StopPoint/{stop.naptan_id}/Arrivals", params=PARAMS)
            response.raise_for_status()
            json = response.json()
            arrivals = TypeAdapter(list[ArrivalUnion]).validate_python(json)
            sortd = sorted(arrivals, key=lambda x: x.time_to_station)
            if isinstance(stop, SingleStopPoint):
                stop_and_arrivals.append(BusArrivalPanel(stop, sortd))
            elif isinstance(stop, MetroStopPoint):
                stop_and_arrivals.append(TubeArrivalPanel(stop, sortd))
            else:
                raise ValueError(f"Unsupported mode: {stop.modes[0]}")
        return stop_and_arrivals
