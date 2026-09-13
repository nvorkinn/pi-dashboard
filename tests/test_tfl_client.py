from unittest.mock import MagicMock

from requests.adapters import HTTPAdapter

from countdown.http import DEFAULT_TIMEOUT
from countdown.models import MetroStopPoint, SingleStopPoint
from countdown.tfl_client import TflClient, _find_stop_child
from display.bus_arrival_panel import BusArrivalPanel
from display.tube_arrival_panel import TubeArrivalPanel

BUS_STOP_JSON = {
    "naptanId": "490000123W",
    "commonName": "Elephant & Castle",
    "modes": ["bus"],
    "additionalProperties": [],
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


def make_bus_stop(naptan_id="490000123W"):
    return SingleStopPoint.model_validate(dict(BUS_STOP_JSON, naptanId=naptan_id))


def make_metro_stop(naptan_id="940GZZLUKNG"):
    return MetroStopPoint.model_validate(dict(METRO_STOP_JSON, naptanId=naptan_id))


def test_find_stop_child_direct_match():
    stop = make_metro_stop()
    assert _find_stop_child(stop, stop.naptan_id) is stop


def test_find_stop_child_nested_match():
    child = make_bus_stop()
    parent = MetroStopPoint.model_validate(dict(METRO_STOP_JSON, children=[BUS_STOP_JSON]))
    found = _find_stop_child(parent, child.naptan_id)
    assert found is not None
    assert found.naptan_id == child.naptan_id


def test_find_stop_child_not_found_returns_none():
    stop = make_metro_stop()
    assert _find_stop_child(stop, "does-not-exist") is None


def test_construction_never_touches_the_network():
    """__init__ must be cheap and unable to fail -- stop resolution is deferred to
    first use, so a flaky TfL API can never prevent a TflClient from being built."""
    client = TflClient(["940GZZLUKNG"], "app-key")
    assert client.stops == []
    assert client.params == {"app_key": "app-key"}


def test_get_page_count_lazily_resolves_stops(monkeypatch):
    client = TflClient(["940GZZLUKNG"])
    get_mock = MagicMock()
    get_mock.return_value.raise_for_status = MagicMock()
    get_mock.return_value.json.return_value = METRO_STOP_JSON
    monkeypatch.setattr(client.session, "get", get_mock)

    assert client.get_page_count() == 1
    assert len(client.stops) == 1
    get_mock.assert_called_once()


def test_get_page_count_empty_when_no_stops_configured():
    client = TflClient([])
    assert client.get_page_count() == 1
    assert client.stops == []


def test_get_page_count_rounds_up():
    client = TflClient([])
    client.stops = [make_bus_stop(), make_metro_stop(), make_bus_stop("490000456X")]
    assert client.get_page_count() == 2


def test_ensure_stops_is_not_repeated_once_populated(monkeypatch):
    client = TflClient(["940GZZLUKNG"])
    get_mock = MagicMock()
    get_mock.return_value.raise_for_status = MagicMock()
    get_mock.return_value.json.return_value = METRO_STOP_JSON
    monkeypatch.setattr(client.session, "get", get_mock)

    client.get_page_count()
    client.get_page_count()

    get_mock.assert_called_once()


def test_failed_setup_leaves_stops_empty_and_is_retried_on_next_call(monkeypatch):
    client = TflClient(["940GZZLUKNG"])
    get_mock = MagicMock(side_effect=ConnectionError("network is down"))
    monkeypatch.setattr(client.session, "get", get_mock)

    assert client.get_next_arrivals() == []
    assert client.stops == []

    # A later call retries setup rather than staying broken forever.
    get_mock.side_effect = None
    get_mock.return_value.raise_for_status = MagicMock()
    get_mock.return_value.json.return_value = METRO_STOP_JSON

    assert client.get_page_count() == 1
    assert len(client.stops) == 1


def test_init_stops_is_a_pure_function_returning_resolved_stops(monkeypatch):
    client = TflClient([])
    get_mock = MagicMock()
    get_mock.return_value.raise_for_status = MagicMock()
    get_mock.return_value.json.return_value = METRO_STOP_JSON
    monkeypatch.setattr(client.session, "get", get_mock)

    result = client.init_stops(["940GZZLUKNG"])

    assert len(result) == 1
    assert client.stops == []  # init_stops does not mutate self


def test_get_next_stop_cycles_and_wraps():
    client = TflClient([])
    a, b = make_bus_stop("A"), make_metro_stop("B")
    client.stops = [a, b]
    assert client._get_next_stop() is a
    assert client._get_next_stop() is b
    assert client._get_next_stop() is a


def test_get_next_arrivals_builds_correct_panels(monkeypatch):
    client = TflClient([])
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

    panels = client.get_next_arrivals()

    assert len(panels) == 2
    assert isinstance(panels[0], BusArrivalPanel)
    assert isinstance(panels[1], TubeArrivalPanel)


def test_get_next_arrivals_skips_stop_on_request_failure(monkeypatch):
    client = TflClient([])
    client.stops = [make_bus_stop()]

    def failing_get(url, params=None, timeout=None):
        raise ConnectionError("network is down")

    monkeypatch.setattr(client.session, "get", failing_get)

    assert client.get_next_arrivals() == []


def test_get_next_arrivals_passes_a_timeout(monkeypatch):
    client = TflClient([])
    client.stops = [make_bus_stop()]

    get_mock = MagicMock()
    get_mock.return_value.raise_for_status = MagicMock()
    get_mock.return_value.json.return_value = [{
        "naptanId": "490000123W", "lineName": "N155", "timeToStation": 300,
        "modeName": "bus", "destinationName": "Somewhere",
    }]
    monkeypatch.setattr(client.session, "get", get_mock)

    client.get_next_arrivals()

    assert get_mock.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT


def test_get_stop_info_passes_a_timeout(monkeypatch):
    client = TflClient([])

    get_mock = MagicMock()
    get_mock.return_value.raise_for_status = MagicMock()
    get_mock.return_value.json.return_value = METRO_STOP_JSON
    monkeypatch.setattr(client.session, "get", get_mock)

    client._get_stop_info("940GZZLUKNG")

    assert get_mock.call_args.kwargs["timeout"] == DEFAULT_TIMEOUT


def test_session_has_retry_adapter_mounted():
    client = TflClient([])
    adapter = client.session.get_adapter("https://api.tfl.gov.uk")
    assert isinstance(adapter, HTTPAdapter)
    assert adapter.max_retries.total == 3
