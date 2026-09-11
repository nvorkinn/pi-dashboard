from collections import defaultdict
from typing import Tuple, Any
import requests
from pydantic import TypeAdapter

from countdown.models import Arrival, StopPointResponse, StopPoint, Mode

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

class TflClient:
    stop_ids = {
        Mode.BUS: [],
        Mode.TUBE: []
    }

    def __init__(self, config: dict):
        for mode in Mode:
            if "stop_ids" in config[mode]:
                self.stop_ids[mode].extend(config[mode]['stop_ids'])
            if "postcode" in config[mode]:
                lat, lon = _get_lat_and_lon(config[mode]['postcode'])
                nearest_stops = _get_nearest_stops(lat, lon, config[mode].get("compass_point"))
                self.stop_ids[mode].extend(nearest_stops)
            # else:
            #     raise ValueError(f"No stop_ids or postcode set in config for {mode}")
        self.session = requests.Session()

    def get_next_departures(self, show_bus: bool) -> list[Any]:
        dep_groups = []
        arrivals_type_adapter = TypeAdapter(list[Arrival])
        mode = Mode.BUS if show_bus else Mode.TUBE
        for stop_id in self.stop_ids[mode]:
            response = self.session.get(f"https://api.tfl.gov.uk/StopPoint/{stop_id}/Arrivals", params=PARAMS)
            response.raise_for_status()
            json = response.json()
            arrivals = arrivals_type_adapter.validate_python(json)
            if not arrivals:
                continue
            sortd = sorted(arrivals, key=lambda x: x.time_to_station)
            if mode == Mode.BUS:
                dep_groups.append((Mode.BUS, sortd, sortd[0].station, stop_id[-1]))
            elif mode == Mode.TUBE:
                dep_groups.append((Mode.TUBE, sortd, sortd[0].station.removesuffix(" Underground Station")))
        return sorted(dep_groups, reverse=True, key=lambda x : len(x[1]))