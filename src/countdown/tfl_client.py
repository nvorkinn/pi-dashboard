from math import ceil

from pydantic import TypeAdapter

from countdown.config_manager import TflConfig
from countdown.http import DEFAULT_TIMEOUT, build_retrying_session
from countdown.models import ArrivalUnion, StopPoint, StopPointUnion, SingleStopPoint, MetroStopPoint
from display.abstract_arrival_panel import AbstractArrivalPanel
from display.bus_arrival_panel import BusArrivalPanel
from display.tube_arrival_panel import TubeArrivalPanel


def _find_stop_child(stop: StopPoint, naptan_id: str) -> SingleStopPoint | MetroStopPoint | None:
    if stop.naptan_id == naptan_id and (isinstance(stop, SingleStopPoint) or isinstance(stop, MetroStopPoint)):
        return stop
    for child in stop.children:
        grandchild = _find_stop_child(child, naptan_id)
        if grandchild is not None:
            return grandchild
    return None


class TflClient:
    def __init__(self, config: TflConfig):
        """Construction never touches the network -- stops are resolved lazily on first
        use (see _ensure_stops), so a flaky TfL API can never prevent this object from
        being created. Safe to just build a fresh TflClient whenever config changes."""
        self._config = config
        self.stops: list[SingleStopPoint | MetroStopPoint] = []
        self.current_stop = 0
        self.params = {"app_key": config.app_key} if config.app_key else {}
        self.session = build_retrying_session()

    def _ensure_stops(self) -> None:
        """Resolve self._config.stop_ids into self.stops if not already done. Safe to
        call repeatedly and safe to fail: self.stops is only ever assigned once fully
        built, so a failed attempt just leaves it empty for the next call to retry."""
        if self.stops:
            return
        self.stops = self.init_stops(self._config.stop_ids)

    def init_stops(self, stop_ids: list[str]) -> list[SingleStopPoint | MetroStopPoint]:
        stops: list[SingleStopPoint | MetroStopPoint] = []
        for stop_id in stop_ids:
            try:
                info = self._get_stop_info(stop_id)
                if info is not None:
                    stops.append(info)
                else:
                    print(f"Warning: Stop ID {stop_id} could not be resolved from TfL API")
            except Exception as e:
                print(f"Warning: Error fetching stop ID {stop_id}: {e}")
        return stops

    def _get_stop_info(self, stop_id: str) -> SingleStopPoint | MetroStopPoint | None:
        response = self.session.get(f"https://api.tfl.gov.uk/StopPoint/{stop_id}", params=self.params, timeout=DEFAULT_TIMEOUT)
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
        self._ensure_stops()
        return ceil(len(self.stops) / 2) if self.stops else 1

    def get_next_arrivals(self) -> list[AbstractArrivalPanel]:
        self._ensure_stops()
        if not self.stops:
            return []
        stop_and_arrivals = []
        count_to_fetch = min(2, len(self.stops))
        for _ in range(count_to_fetch):
            stop = self._get_next_stop()
            try:
                response = self.session.get(f"https://api.tfl.gov.uk/StopPoint/{stop.naptan_id}/Arrivals", params=self.params, timeout=DEFAULT_TIMEOUT)
                response.raise_for_status()
                json = response.json()
                arrivals = TypeAdapter(list[ArrivalUnion]).validate_python(json)
                sortd = sorted(arrivals, key=lambda x: x.time_to_station)
                if isinstance(stop, SingleStopPoint):
                    stop_and_arrivals.append(BusArrivalPanel(stop, sortd))
                elif isinstance(stop, MetroStopPoint):
                    stop_and_arrivals.append(TubeArrivalPanel(stop, sortd))
            except Exception as e:
                print(f"Error fetching arrivals for stop {stop.naptan_id}: {e}")
        return stop_and_arrivals
