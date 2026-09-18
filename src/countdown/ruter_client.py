"""Client for fetching public transport arrivals and departures in Oslo / Norway.

In Oslo, Ruter operates the public transport network (metro/T-bane, tram/trikk,
bus, and ferries). The transit data is standardized nationally and served via
Entur's JourneyPlanner GraphQL API (Transmodel / NeTEx compliant).

This client is mode-agnostic, meaning the exact same queries and data structures
handle bus, tram, metro, rail, and ferry departures.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from math import ceil
from typing import Any

import requests
from pydantic import BaseModel, Field


class TransportMode(StrEnum):
    BUS = "bus"
    TRAM = "tram"
    METRO = "metro"
    RAIL = "rail"
    WATER = "water"
    COACH = "coach"
    AIR = "air"
    UNKNOWN = "unknown"

    @classmethod
    def from_str(cls, value: str | None) -> TransportMode:
        if not value:
            return cls.UNKNOWN
        val = value.lower()
        for mode in cls:
            if mode.value == val:
                return mode
        return cls.UNKNOWN


class RuterDeparture(BaseModel):
    """Normalized departure model, mode-agnostic across bus, tram, metro, etc."""
    line: str = Field(description="Line number / public code, e.g. '31', '5', '12'")
    line_name: str | None = Field(default=None, description="Descriptive line name")
    destination: str = Field(description="Destination front text, e.g. 'Sognsvann'")
    mode: TransportMode = Field(description="Transport mode: bus, tram, metro, rail, etc.")
    aimed_departure_time: datetime
    expected_departure_time: datetime
    aimed_arrival_time: datetime | None = None
    expected_arrival_time: datetime | None = None
    time_to_station: int = Field(
        description="Seconds until departure from current time (compatible with Countdown/TfL models)"
    )
    minutes_to_station: int = Field(description="Minutes until departure (rounded)")
    realtime: bool = True
    cancelled: bool = False
    stop_id: str
    stop_name: str
    quay_id: str | None = None
    quay_code: str | None = Field(default=None, description="Platform/track code, e.g. '1', '2', 'A'")


class RuterStop(BaseModel):
    """Metadata for a stop place or quay."""
    id: str
    name: str
    transport_modes: list[TransportMode] = Field(default_factory=list)


# GraphQL query for a StopPlace (e.g. NSR:StopPlace:59872 - Jernbanetorget)
_STOP_PLACE_QUERY = """
query GetStopPlaceDepartures($id: String!, $numberOfDepartures: Int = 10, $startTime: DateTime) {
  stopPlace(id: $id) {
    id
    name
    transportMode
    estimatedCalls(numberOfDepartures: $numberOfDepartures, startTime: $startTime) {
      realtime
      cancellation
      aimedDepartureTime
      expectedDepartureTime
      aimedArrivalTime
      expectedArrivalTime
      destinationDisplay {
        frontText
      }
      quay {
        id
        publicCode
        name
      }
      serviceJourney {
        id
        transportMode
        transportSubmode
        line {
          id
          publicCode
          name
          transportMode
        }
      }
    }
  }
}
"""

# GraphQL query for a specific Quay (e.g. NSR:Quay:102047)
_QUAY_QUERY = """
query GetQuayDepartures($id: String!, $numberOfDepartures: Int = 10, $startTime: DateTime) {
  quay(id: $id) {
    id
    name
    stopPlace {
      id
      name
      transportMode
    }
    estimatedCalls(numberOfDepartures: $numberOfDepartures, startTime: $startTime) {
      realtime
      cancellation
      aimedDepartureTime
      expectedDepartureTime
      aimedArrivalTime
      expectedArrivalTime
      destinationDisplay {
        frontText
      }
      quay {
        id
        publicCode
        name
      }
      serviceJourney {
        id
        transportMode
        transportSubmode
        line {
          id
          publicCode
          name
          transportMode
        }
      }
    }
  }
}
"""


def _normalize_stop_id(stop_id: str | int) -> str:
    """Ensure stop ID has the proper NSR prefix."""
    s = str(stop_id).strip()
    if s.startswith("NSR:"):
        return s
    # Default to StopPlace if numeric or unspecified
    return f"NSR:StopPlace:{s}"


class RuterClient:
    """Client for Ruter / Entur public transport API in Oslo and Norway.

    Can be used standalone or initialized with a list of stop IDs.
    Works mode-agnostically for buses, trams, metro (T-bane), rail, and ferries.
    """

    JOURNEY_PLANNER_URL = "https://api.entur.io/journey-planner/v3/graphql"
    GEOCODER_URL = "https://api.entur.io/geocoder/v1"

    def __init__(
        self,
        stop_ids: list[str | int] | None = None,
        client_name: str = "countdown-oslo-ruter",
        session: requests.Session | None = None,
    ):
        """
        Initialize the Ruter / Entur client.

        Args:
            stop_ids: List of stop place IDs (e.g. ['NSR:StopPlace:59872'] or numeric IDs).
            client_name: ET-Client-Name identifying your application to Entur (required by Entur ToS).
            session: Optional existing requests.Session.
        """
        self.client_name = client_name
        self.session = session or requests.Session()
        self.session.headers.update({
            "ET-Client-Name": self.client_name,
            "Content-Type": "application/json",
        })

        self.stops: list[RuterStop] = []
        self.current_stop_index: int = 0

        if stop_ids:
            self.init_stops(stop_ids)

    def init_stops(self, stop_ids: list[str | int]) -> None:
        """Fetch metadata for a list of stop IDs and store them for cycle display."""
        self.stops.clear()
        for raw_id in stop_ids:
            stop_id = _normalize_stop_id(raw_id)
            try:
                info = self.get_stop_info(stop_id)
                if info:
                    self.stops.append(info)
                else:
                    print(f"Warning: Stop ID {stop_id} could not be resolved from Entur API")
            except Exception as e:
                print(f"Warning: Error fetching stop ID {stop_id}: {e}")

    def _execute_graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Send a GraphQL POST request to Entur JourneyPlanner."""
        response = self.session.post(
            self.JOURNEY_PLANNER_URL,
            json={"query": query, "variables": variables},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if "errors" in payload:
            error_msgs = ", ".join(err.get("message", str(err)) for err in payload["errors"])
            raise RuntimeError(f"GraphQL error from Entur API: {error_msgs}")
        return payload.get("data", {})

    def get_stop_info(self, stop_id: str | int) -> RuterStop | None:
        """Fetch metadata for a stop place or quay."""
        normalized_id = _normalize_stop_id(stop_id)
        is_quay = normalized_id.startswith("NSR:Quay:")
        query = _QUAY_QUERY if is_quay else _STOP_PLACE_QUERY

        data = self._execute_graphql(query, {"id": normalized_id, "numberOfDepartures": 1})

        if is_quay:
            quay_data = data.get("quay")
            if not isinstance(quay_data, dict):
                return None
            parent = quay_data.get("stopPlace")
            parent_dict = parent if isinstance(parent, dict) else {}
            raw_modes = parent_dict.get("transportMode") or []
            return RuterStop(
                id=str(quay_data.get("id", normalized_id)),
                name=quay_data.get("name") or parent_dict.get("name") or "Unknown Stop",
                transport_modes=[TransportMode.from_str(m) for m in raw_modes],
            )

        stop_data = data.get("stopPlace")
        if not isinstance(stop_data, dict):
            return None

        raw_modes = stop_data.get("transportMode") or []
        return RuterStop(
            id=str(stop_data.get("id", normalized_id)),
            name=stop_data.get("name") or "Unknown Stop",
            transport_modes=[TransportMode.from_str(m) for m in raw_modes],
        )

    def get_departures(
        self,
        stop_id: str | int,
        limit: int = 10,
        modes: list[TransportMode | str] | None = None,
        now: datetime | None = None,
    ) -> list[RuterDeparture]:
        """
        Get the list of next departures for any stop place or quay.

        Mode-agnostic: automatically handles bus, tram, metro, train, and boat.

        Args:
            stop_id: Entur StopPlace or Quay ID (e.g. 'NSR:StopPlace:59872' or 59872).
            limit: Maximum number of departures to return.
            modes: Optional list of modes to filter by (e.g. [TransportMode.METRO, TransportMode.BUS]).
                   If None or empty, departures of ALL modes are returned.
            now: Current reference time (defaults to datetime.now(timezone.utc)).

        Returns:
            List of RuterDeparture objects sorted by departure time.
        """
        ref_time = now or datetime.now(UTC)
        normalized_id = _normalize_stop_id(stop_id)
        is_quay = normalized_id.startswith("NSR:Quay:")
        query = _QUAY_QUERY if is_quay else _STOP_PLACE_QUERY

        # Fetch extra departures to allow for filtering and cancellations
        fetch_count = limit * 2 if modes else limit
        data = self._execute_graphql(
            query,
            {"id": normalized_id, "numberOfDepartures": fetch_count, "startTime": ref_time.isoformat()},
        )

        container = data.get("quay") if is_quay else data.get("stopPlace")
        if not isinstance(container, dict):
            return []

        stop_name = container.get("name") or "Unknown"
        raw_calls = container.get("estimatedCalls")
        if not isinstance(raw_calls, list):
            return []

        allowed_modes = None
        if modes:
            allowed_modes = {
                m if isinstance(m, TransportMode) else TransportMode.from_str(str(m))
                for m in modes
            }

        departures: list[RuterDeparture] = []

        for call in raw_calls:
            if not isinstance(call, dict):
                continue
            service = call.get("serviceJourney") or {}
            line_info = service.get("line") or {}

            # Mode can be specified on line or serviceJourney
            raw_mode = line_info.get("transportMode") or service.get("transportMode")
            mode = TransportMode.from_str(raw_mode)

            if allowed_modes and mode not in allowed_modes:
                continue

            # Departure time parsing
            exp_dep_str = call.get("expectedDepartureTime") or call.get("aimedDepartureTime")
            if not exp_dep_str:
                # If terminal arrival with no departure time, fallback to expectedArrivalTime
                exp_dep_str = call.get("expectedArrivalTime") or call.get("aimedArrivalTime")

            if not exp_dep_str:
                continue

            exp_dep_time = datetime.fromisoformat(exp_dep_str)
            aim_dep_str = call.get("aimedDepartureTime") or exp_dep_str
            aim_dep_time = datetime.fromisoformat(aim_dep_str)

            exp_arr_time = datetime.fromisoformat(call["expectedArrivalTime"]) if call.get("expectedArrivalTime") else None
            aim_arr_time = datetime.fromisoformat(call["aimedArrivalTime"]) if call.get("aimedArrivalTime") else None

            # Calculate seconds to departure
            seconds = int((exp_dep_time - ref_time).total_seconds())
            if seconds < -60:
                # Skip departures already gone over 1 minute ago
                continue

            time_to_station = max(0, seconds)
            minutes_to_station = int(ceil(time_to_station / 60))

            dest_display = call.get("destinationDisplay") or {}
            destination = dest_display.get("frontText") or "Unknown destination"

            quay_info = call.get("quay") or {}

            departures.append(
                RuterDeparture(
                    line=line_info.get("publicCode") or line_info.get("name") or "?",
                    line_name=line_info.get("name"),
                    destination=destination,
                    mode=mode,
                    aimed_departure_time=aim_dep_time,
                    expected_departure_time=exp_dep_time,
                    aimed_arrival_time=aim_arr_time,
                    expected_arrival_time=exp_arr_time,
                    time_to_station=time_to_station,
                    minutes_to_station=minutes_to_station,
                    realtime=call.get("realtime", True),
                    cancelled=call.get("cancellation", False),
                    stop_id=normalized_id,
                    stop_name=stop_name,
                    quay_id=quay_info.get("id"),
                    quay_code=quay_info.get("publicCode"),
                )
            )

            if len(departures) >= limit:
                break

        departures.sort(key=lambda d: d.time_to_station)
        return departures

    def get_next_departures(self, count_stops: int = 2, limit_per_stop: int = 5) -> list[tuple[RuterStop, list[RuterDeparture]]]:
        """
        Cycle through configured stops and return departures for the next batch of stops.
        Mirrors the paging behavior in TfLClient.
        """
        if not self.stops:
            return []

        results = []
        count = min(count_stops, len(self.stops))
        for _ in range(count):
            stop = self.stops[self.current_stop_index]
            self.current_stop_index = (self.current_stop_index + 1) % len(self.stops)
            try:
                departures = self.get_departures(stop.id, limit=limit_per_stop)
                results.append((stop, departures))
            except Exception as e:
                print(f"Error fetching departures for Ruter stop {stop.id}: {e}")

        return results

    def get_page_count(self) -> int:
        """Return total display pages if cycling 2 stops at a time."""
        return ceil(len(self.stops) / 2) if self.stops else 1

    def search_stops(self, query: str, size: int = 5) -> list[dict[str, Any]]:
        """
        Search for stop places by name using Entur's Geocoder autocomplete API.

        Example:
            client.search_stops("Jernbanetorget")
            client.search_stops("Majorstuen")
            client.search_stops("Alexander Kiellands plass")
        """
        params = {
            "text": query,
            "size": size,
            "layers": "venue",  # Only transit venues (stops/stations)
        }
        url = f"{self.GEOCODER_URL}/autocomplete"
        response = self.session.get(url, params=params, timeout=10)
        response.raise_for_status()

        features = response.json().get("features", [])
        results = []
        for feat in features:
            props = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [0, 0])
            results.append({
                "id": props.get("id"),
                "name": props.get("name"),
                "locality": props.get("locality"),
                "county": props.get("county"),
                "category": props.get("category", []),
                "coordinates": {"lon": coords[0], "lat": coords[1]},
            })
        return results

    def get_nearest_stops(self, lat: float, lon: float, size: int = 5) -> list[dict[str, Any]]:
        """
        Find transit stops nearest to a given GPS latitude and longitude.

        Uses Entur's reverse geocoder.
        """
        params = {
            "point.lat": lat,
            "point.lon": lon,
            "size": size,
            "layers": "venue",
        }
        url = f"{self.GEOCODER_URL}/reverse"
        response = self.session.get(url, params=params, timeout=10)
        response.raise_for_status()

        features = response.json().get("features", [])
        results = []
        for feat in features:
            props = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [0, 0])
            results.append({
                "id": props.get("id"),
                "name": props.get("name"),
                "locality": props.get("locality"),
                "distance": props.get("distance"),
                "category": props.get("category", []),
                "coordinates": {"lon": coords[0], "lat": coords[1]},
            })
        return results
