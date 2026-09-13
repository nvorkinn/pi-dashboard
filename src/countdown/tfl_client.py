from typing import Tuple
import requests
from math import ceil
from pydantic import TypeAdapter

from countdown.config_manager import AppConfig
from countdown.models import StopPointResponse, StopPoint, ArrivalUnion, StopPointUnion, SingleStopPoint, \
    MetroStopPoint
from display.abstract_arrival_panel import AbstractArrivalPanel
from display.bus_arrival_panel import BusArrivalPanel
from display.tube_arrival_panel import TubeArrivalPanel

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
    def __init__(self, config: AppConfig):
        self.stops: list[SingleStopPoint | MetroStopPoint] = []
        self.current_stop = 0
        self.params = {"app_key": config.tfl_api_app_key} if config.tfl_api_app_key else {}
        self.session = requests.Session()

        # If a flat ordered list of stops is configured, use it directly
        if config.stops:
            stop_ids = list(config.stops)
        else:
            stop_ids = []
            stop_ids.extend(config.bus.stop_ids)
            if config.bus.postcode:
                lat, lon = _get_lat_and_lon(config.bus.postcode)
                nearest_stops = _get_nearest_stops(lat, lon, config.bus.compass_point)
                stop_ids.extend(nearest_stops)
            stop_ids.extend(config.tube.stop_ids)

        self.init_stops(stop_ids)

    def init_stops(self, stop_ids: list[str]) -> None:
        self.stops.clear()
        for stop_id in stop_ids:
            try:
                info = self._get_stop_info(stop_id)
                if info is not None:
                    self.stops.append(info)
                else:
                    print(f"Warning: Stop ID {stop_id} could not be resolved from TfL API")
            except Exception as e:
                print(f"Warning: Error fetching stop ID {stop_id}: {e}")

    def _get_stop_info(self, stop_id: str) -> SingleStopPoint | MetroStopPoint | None:
        response = self.session.get(f"https://api.tfl.gov.uk/StopPoint/{stop_id}", params=self.params)
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

    def get_page_count(self) -> int:
        return ceil(len(self.stops) / 2) if self.stops else 1

    def get_next_departures(self) -> list[AbstractArrivalPanel]:
        if not self.stops:
            return []
        stop_and_arrivals = []
        count_to_fetch = min(2, len(self.stops))
        for _ in range(count_to_fetch):
            stop = self._get_next_stop()
            try:
                response = self.session.get(f"https://api.tfl.gov.uk/StopPoint/{stop.naptan_id}/Arrivals", params=self.params)
                response.raise_for_status()
                json = response.json()
                arrivals = TypeAdapter(list[ArrivalUnion]).validate_python(json)
                sortd = sorted(arrivals, key=lambda x: x.time_to_station)
                if isinstance(stop, SingleStopPoint):
                    stop_and_arrivals.append(BusArrivalPanel(stop, sortd))
                elif isinstance(stop, MetroStopPoint):
                    stop_and_arrivals.append(TubeArrivalPanel(stop, sortd))
            except Exception as e:
                print(f"Error fetching departures for stop {stop.naptan_id}: {e}")
        return stop_and_arrivals
