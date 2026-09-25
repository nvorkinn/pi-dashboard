from datetime import UTC, datetime, timedelta
from math import floor

from pydantic import TypeAdapter

from countdown.abstract_client import AbstractClient, ClientStatus
from countdown.config_manager import GlowmarktConfig
from countdown.http import DEFAULT_TIMEOUT, build_retrying_session
from countdown.models import Entity, Readings
from display.energy_panel import EnergyPanel


def _get_utc_offset(now: datetime | None = None) -> str:
    # Evaluated per call, not as a default argument: that would freeze the offset at
    # import time, wrong for a long-running device after the clocks change.
    utc_offset = (now or datetime.now()).astimezone().utcoffset()
    if utc_offset is None:
        raise ValueError("Could not find a UTC offset")
    offset_int: int = floor(utc_offset.seconds * -1 / 60)
    return str(offset_int)


class GlowClient(AbstractClient):
    poll_interval = timedelta(minutes=15)
    panel_title = "Energy"
    base_url = "https://api.glowmarkt.com/api/v0-1"
    app_id = "b0f1b774-a586-4f72-9edd-27ead8aa7a8d"
    resource_id = None
    token = None

    def __init__(self, config: GlowmarktConfig):
        super().__init__(config)
        self.page_index = 0
        self.username = config.username
        self.password = config.password
        self.glow_cache = {0: {}, 1: {}, 2: {}}
        self.session = build_retrying_session()
        if not config.username or not config.password:
            self.status = ClientStatus.DISABLED

    def _initialise(self) -> None:
        self._authenticate()
        self.resource_id = self.get_electricity_resource_id()

    def _authenticate(self):
        """Internal method to fetch and store the session token."""
        url = f"{self.base_url}/auth"
        payload = {"username": self.username, "password": self.password, "applicationId": self.app_id}
        response = self.session.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()

        # Adjust key based on the actual Glowmarkt token response structure
        self.token = response.json().get("token")

    def _request(self, method: str, endpoint: str, params: dict[str, str] | None = None):
        """Centralised request wrapper implementing lazy authentication."""
        if not self.token:
            self._authenticate()
        if not self.token:
            return None

        headers = {"token": self.token, "applicationId": self.app_id, "Content-Type": "application/json"}

        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)

        # Handle token expiration (HTTP 401 Unauthorized) gracefully
        if response.status_code == 401:
            self._authenticate()
            if not self.token:
                return None
            headers["token"] = self.token
            response = self.session.request(method, url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)

        response.raise_for_status()
        return response.json()

    def get_electricity_resource_id(self):
        json = self._request("GET", "/virtualentity")
        entity_list_adapter = TypeAdapter(list[Entity])
        entities = entity_list_adapter.validate_python(json)
        for resource in entities[0].resources:
            if resource.name == "electricity consumption":
                return resource.resourceId
        raise ValueError("Could not find a resource with name 'electricity consumption'")

    def _update(self) -> EnergyPanel:
        current = datetime.now().astimezone()
        window_start, period, bucket_delta = self._page_config(self.page_index, current)
        open_start = self._truncate(current, period)

        # Align the window start to a bucket boundary too - otherwise it
        # never matches the (bucket-aligned) keys already sitting in the
        # cache, and every call looks like a cache miss.
        window_start = self._truncate(window_start, period)

        cache = self.glow_cache[self.page_index]
        # Walk forward from window_start to open_start to see which closed
        # buckets we SHOULD have, and whether any of them are missing from
        # the cache (true on first run, or after the window has slid forward).
        missing_from = None
        cursor = window_start
        while cursor < open_start:
            if cursor not in cache:
                missing_from = cursor if missing_from is None else missing_from
            cursor = self._next_bucket_start(cursor, period, bucket_delta)

        if missing_from is not None:
            # Catch up: fetch everything from the earliest gap through to now.
            fetched = self._get_readings(missing_from, current, period)
        else:
            # Everything closed is already cached - only ask for the one
            # bucket that's still live.
            fetched = self._get_readings(open_start, current, period)

        open_value: float | None = None
        for bucket_start, value in fetched:
            if bucket_start < open_start:
                cache[bucket_start] = value  # closed - safe to keep forever
            else:
                open_value = value  # open - never cached, always fresh

        # Drop anything that's aged out of a sliding window (pages 0 and 1;
        # page 2's window start is fixed to 1st Jan so nothing ever ages out).
        for stale in [b for b in cache if b < window_start]:
            del cache[stale]

        usage = [
            {"start": bucket_start.isoformat(), "kwh": round(value, 3)} for bucket_start, value in sorted(cache.items())
        ]
        if open_value is not None:
            usage.append({"start": open_start.isoformat(), "kwh": round(open_value, 3)})

        self.glow_cache[self.page_index] = cache
        panel = EnergyPanel(usage, self.page_index)
        self.page_index = (self.page_index + 1) % 3
        return panel

    def _page_config(self, page_index: int, current: datetime) -> tuple[datetime, str, timedelta]:
        if page_index == 0:
            window_start = current - timedelta(hours=24)
            return window_start, "PT1H", timedelta(hours=1)
        elif page_index == 1:
            window_start = current - timedelta(days=31)
            return window_start, "P1D", timedelta(days=1)
        elif page_index == 2:
            window_start = current.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            return window_start, "P1M", timedelta()  # months handled specially below
        else:
            raise ValueError(f"page_index must be 0, 1 or 2 - got {page_index}")

    def _truncate(self, dt: datetime, period: str) -> datetime:
        """Round a datetime down to the start of its bucket."""
        if period == "PT1H":
            return dt.replace(minute=0, second=0, microsecond=0)
        elif period == "P1D":
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        else:  # period == "P1M"
            return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _next_bucket_start(self, dt: datetime, period: str, bucket_delta: timedelta):
        """Step forward exactly one bucket - months aren't a fixed length,
        so they need their own bit of arithmetic instead of a timedelta."""
        if period == "P1M":
            if dt.month == 12:
                return dt.replace(year=dt.year + 1, month=1)
            return dt.replace(month=dt.month + 1)
        return dt + bucket_delta

    def _get_readings(self, dt_from: datetime, dt_to: datetime, period: str) -> list[Readings]:
        """
        period: "PT1H" (hour), "P1D" (day), or "P1M" (month) - the API's own
        aggregation does the summing, so a month request genuinely returns
        ~12 numbers, not raw half-hourly data.

        Returns a list of (datetime, kwh) tuples.
        """

        response = self.session.get(
            f"{self.base_url}/resource/{self.resource_id}/readings",
            headers={"applicationId": self.app_id, "token": self.token},
            params={
                "from": dt_from.strftime("%Y-%m-%dT%H:%M:%S"),
                "to": dt_to.strftime("%Y-%m-%dT%H:%M:%S"),
                "period": period,
                "offset": _get_utc_offset(),
                "function": "sum",
            },
        )
        response.raise_for_status()

        readings = []
        for ts, value in response.json()["data"]:
            # The API has returned both Unix-epoch-seconds and ISO strings
            # across different versions/resources in the wild, so handle both.
            if isinstance(ts, (int, float)):
                bucket_start = datetime.fromtimestamp(ts, tz=UTC)
            else:
                bucket_start = datetime.fromisoformat(ts).replace(tzinfo=UTC)
            readings.append((bucket_start, value))

        return readings
