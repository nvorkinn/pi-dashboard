from datetime import datetime

import requests
from math import floor

from pydantic import TypeAdapter

from countdown.models import Entity, Readings


def _get_utc_offset(now: datetime) -> str:
    utc_offset = now.astimezone().utcoffset()
    if utc_offset is None:
        raise ValueError("Could not find a UTC offset")
    offset_int: int = floor(utc_offset.seconds * -1 / 60)
    return str(offset_int)


class GlowClient:
    base_url = 'https://api.glowmarkt.com/api/v0-1'
    app_id = 'b0f1b774-a586-4f72-9edd-27ead8aa7a8d'
    username = 'n.vorkinn@gmail.com'
    password = 'mazzot-purze0-jyrQyf'

    def __init__(self, _config: dict):
        self.session = requests.Session()
        self.token: str | None = None

    def _authenticate(self):
        """Internal method to fetch and store the session token."""
        url = f"{self.base_url}/auth"
        payload = {
            "username": self.username,
            "password": self.password,
            "applicationId": self.app_id
        }
        response = requests.post(url, json=payload)
        response.raise_for_status()

        # Adjust key based on the actual Glowmarkt token response structure
        self.token = response.json().get("token")

    def _request(self, method: str, endpoint: str, params: dict[str, str] | None = None):
        """Centralised request wrapper implementing lazy authentication."""
        if not self.token:
            self._authenticate()
        if not self.token:
            return None

        headers = {
            "token": self.token,
            "applicationId": self.app_id,
            "Content-Type": "application/json"
        }

        url = f"{self.base_url}{endpoint}"
        response = requests.request(method, url, params=params, headers=headers)

        # Handle token expiration (HTTP 401 Unauthorized) gracefully
        if response.status_code == 401:
            self._authenticate()
            if not self.token:
                return None
            headers["token"] = self.token
            response = requests.request(method, url, params=params, headers=headers)

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

    def get_day_readings(self, resource_id: str) -> list[float]:
        now = datetime.now()
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        params = {
            "period": "PT1H",
            "from": start_of_today.isoformat(timespec="seconds"),
            "to": now.isoformat(timespec="seconds"),
            "offset": _get_utc_offset(now),
            "function": "sum"
        }
        json = self._request("GET", f"/resource/{resource_id}/readings", params=params)
        readings = Readings.model_validate(json)
        return [reading[1] for reading in readings.data]

    def get_month_readings(self, resource_id: str) -> list[float]:
        now = datetime.now()
        start_of_month = datetime(now.year, now.month, 1)
        params = {
            "period": "P1D",
            "from": start_of_month.isoformat(timespec="seconds"),
            "to": now.isoformat(timespec="seconds"),
            "offset": _get_utc_offset(now),
            "function": "sum"
        }
        json = self._request("GET", f"/resource/{resource_id}/readings", params=params)
        readings = Readings.model_validate(json)
        return [reading[1] for reading in readings.data]

    def get_year_readings(self, resource_id: str) -> list[float]:
        now = datetime.now()
        start_of_year = datetime(now.year, 1, 1)
        params = {
            "period": "P1M",
            "from": start_of_year.isoformat(timespec="seconds"),
            "to": now.isoformat(timespec="seconds"),
            "offset": _get_utc_offset(now),
            "function": "sum"
        }
        json = self._request("GET", f"/resource/{resource_id}/readings", params=params)
        readings = Readings.model_validate(json)
        return [reading[1] for reading in readings.data]