from typing import Tuple
import requests

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

    return [
        stop['naptanId']
        for stop in json.get("stopPoints", []) if _is_stop_in_right_direction(stop, compass_point)
    ]

def _is_stop_in_right_direction(stop: dict, desired_direction: str | None) -> bool:
    if desired_direction is None:
        return True
    for additional_property in stop['additionalProperties']:
        if additional_property['key'] == "CompassPoint":
            return additional_property['value'] == desired_direction
    return True # If there is no CompassPoint, include it

def _get_time_text(minutes: int) -> str:
    match minutes:
        case 0:
            return "due"
        case 1:
            return "1 min"
        case _:
            return f"{minutes} mins"


class TflClient:
    def __init__(self, config: dict):
        if "stop_ids" in config:
            self.stop_ids = config['stop_ids']
        elif "postcode" in config:
            lat, lon = _get_lat_and_lon(config['postcode'])
            self.stop_ids = _get_nearest_stops(lat, lon, config.get("compass_point"))
        else:
            raise ValueError("No stop_ids or postcode set in config")
        self.session = requests.Session()

    def get_next_departures(self) -> list[dict[str, str]]:
        all_arrivals = []
        for stop_id in self.stop_ids:
            stop = stop_id[-1:]
            response = self.session.get(f"https://api.tfl.gov.uk/StopPoint/{stop_id}/Arrivals", params=PARAMS)
            response.raise_for_status()
            arrivals = response.json()
            for arrival in arrivals: arrival['stop'] = stop
            all_arrivals.extend(arrivals)

        next_five = sorted(all_arrivals, key=lambda x: x['timeToStation'])[:5]
        return [
            {
                "route": arrival['lineName'],
                "destination" : arrival['destinationName'].split(",")[0],
                "stop": arrival['stop'],
                "time": _get_time_text(arrival['timeToStation'] // 60),
            }
            for arrival in next_five
        ]