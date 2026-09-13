from unittest.mock import MagicMock

from requests.adapters import HTTPAdapter

from countdown.config_manager import AppConfig
from countdown.http import DEFAULT_TIMEOUT
from countdown.models import AdditionalProperty, MetroStopPoint, SingleStopPoint
from countdown.tfl_client import TflClient, _find_stop_child, _get_lat_and_lon, _get_nearest_stops, _is_stop_in_right_direction
from display.bus_arrival_panel import BusArrivalPanel
from display.tube_arrival_panel import TubeArrivalPanel

BUS_STOP_JSON = {
    "naptanId": "490000123W",
    "commonName": "Elephant & Castle",
    "modes": ["bus"],
    "additionalProperties": [{"key": "CompassPoint", "value": "N"}],
    "children": [],
    "stopType": "NaptanPublicBusCoachTram",
    "stopLetter": "W",
}

METRO_STOP_JSON = {
    "naptanId": "940GZZLUKNG",
    "commonName": "Kennington Underground Station",
    "modes": ["tube"],
    "additionalProperties": [],
    "children": [],
    "stopType": "NaptanMetroStation",
}


def make_bus_stop(naptan_id="490000123W", compass_point="N"):
    data = dict(BUS_STOP_JSON, naptanId=naptan_id)
    data["additionalProperties"] = [{"key": "CompassPoint", "value": compass_point}] if compass_point else []
    return SingleStopPoint.model_validate(data)


def make_metro_stop(naptan_id="940GZZLUKNG"):
    return MetroStopPoint.model_validate(dict(METRO_STOP_JSON, naptanId=naptan_id))


def empty_client() -> TflClient:
    """A TflClient with no configured stops, so __init__ never hits the network."""
    return TflClient(AppConfig())


def test_is_stop_in_right_direction_matches():
    stop = make_bus_stop(compass_point="N")
    assert _is_stop_in_right_direction(stop, "N") is True
    assert _is_stop_in_right_direction(stop, "S") is False


def test_is_stop_in_right_direction_no_preference():
    stop = make_bus_stop(compass_point="N")
    assert _is_stop_in_right_direction(stop, None) is True


def test_is_stop_in_right_direction_missing_compass_point_included():
    stop = make_bus_stop(compass_point=None)
    assert _is_stop_in_right_direction(stop, "N") is True


def test_find_stop_child_direct_match():
    stop = make_metro_stop()
    assert _find_stop_child(stop, stop.naptan_id) is stop


def test_find_stop_child_nested_match():
    child = make_bus_stop()
    parent_json = dict(METRO_STOP_JSON, children=[BUS_STOP_JSON])
    parent = MetroStopPoint.model_validate(parent_json)
    found = _find_stop_child(parent, child.naptan_id)
    assert found is not None
    assert found.naptan_id == child.naptan_id


def test_find_stop_child_not_found_returns_none():
    stop = make_metro_stop()
    assert _find_stop_child(stop, "does-not-exist") is None


def test_get_page_count_empty():
    client = empty_client()
    assert client.get_page_count() == 1


def test_get_page_count_rounds_up():
    client = empty_client()
    client.stops = [make_bus_stop(), make_metro_stop(), make_bus_stop("490000456X")]
    assert client.get_page_count() == 2


def test_get_next_stop_cycles_and_wraps():
    client = empty_client()
    a, b = make_bus_stop("A"), make_metro_stop("B")
    client.stops = [a, b]
    assert client._get_next_stop() is a
    assert client._get_next_stop() is b
    assert client._get_next_stop() is a


def test_get_next_departures_builds_correct_panels(monkeypatch):
    client = empty_client()
    client.stops = [make_bus_stop(), make_metro_stop()]

    def fake_get(url, params=None, timeout=None):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        if "490000123W" in url:
            response.json.return_value = [{
                "naptanId": "490000123W", "lineName": "N155", "timeToStation": 300,
                "modeName": "bus", "destinationName": "Somewhere",
            }]
        else:
            response.json.return_value = [{
                "naptanId": "940GZZLUKNG", "lineName": "Northern", "timeToStation": 120,
                "modeName": "tube", "towards": "Bank", "destinationNaptanId": None,
            }]
        return response

    monkeypatch.setattr(client.session, "get", fake_get)

    panels = client.get_next_departures()

    assert len(panels) == 2
    assert isinstance(panels[0], BusArrivalPanel)
    assert isinstance(panels[1], TubeArrivalPanel)


def test_get_next_departures_skips_stop_on_request_failure(monkeypatch):
    client = empty_client()
    client.stops = [make_bus_stop()]

    def failing_get(url, params=None, timeout=None):
        raise ConnectionError("network is down")

    monkeypatch.setattr(client.session, "get", failing_get)

    panels = client.get_next_departures()

    assert panels == []


def test_get_next_departures_passes_a_timeout(monkeypatch):
    client = empty_client()
    client.stops = [make_bus_stop()]

    get_mock = MagicMock()
    get_mock.return_value.raise_for_status = MagicMock()
    get_mock.return_value.json.return_value = [{
        "naptanId": "490000123W", "lineName": "N155", "timeToStation": 300,
        "modeName": "bus", "destinationName": "Somewhere",
    }]
    monkeypatch.setattr(client.session, "get", get_mock)

    client.get_next_departures()

    assert get_mock.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT


def test_get_stop_info_passes_a_timeout(monkeypatch):
    client = empty_client()

    get_mock = MagicMock()
    get_mock.return_value.raise_for_status = MagicMock()
    get_mock.return_value.json.return_value = METRO_STOP_JSON
    monkeypatch.setattr(client.session, "get", get_mock)

    client._get_stop_info("940GZZLUKNG")

    assert get_mock.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT


def test_get_lat_and_lon_passes_a_timeout():
    session = MagicMock()
    session.get.return_value.raise_for_status = MagicMock()
    session.get.return_value.json.return_value = {"result": {"latitude": 51.5, "longitude": -0.1}}

    _get_lat_and_lon("SE17 2PX", session)

    assert session.get.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT


def test_get_nearest_stops_passes_a_timeout():
    session = MagicMock()
    session.get.return_value.raise_for_status = MagicMock()
    session.get.return_value.json.return_value = {"stopPoints": []}

    _get_nearest_stops(51.5, -0.1, session)

    assert session.get.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT


def test_session_has_retry_adapter_mounted():
    client = empty_client()
    adapter = client.session.get_adapter("https://api.tfl.gov.uk")
    assert isinstance(adapter, HTTPAdapter)
    assert adapter.max_retries.total == 3
