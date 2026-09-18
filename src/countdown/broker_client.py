import json
import secrets
from pathlib import Path

from pydantic import BaseModel

from countdown.http import DEFAULT_TIMEOUT, build_retrying_session

CREDENTIALS_FILE = Path(".auth_broker_device")


class BrokerTflConfig(BaseModel):
    app_key: str
    stop_ids: list[str]


class BrokerWeatherConfig(BaseModel):
    api_key: str
    location: str


class BrokerSpotifyConfig(BaseModel):
    enabled: bool


class BrokerConfig(BaseModel):
    interval: int
    tfl: BrokerTflConfig
    weather: BrokerWeatherConfig
    spotify: BrokerSpotifyConfig


class BrokerClient:
    """Talks to auth-broker (https://github.com/nvorkinn/auth-broker), the cloud
    service that handles Spotify OAuth and hosts this device's config centrally --
    gifted frames have no stable public address of their own, so the broker is the
    one place that needs real TLS.

    Registers itself on first run, persisting credentials to CREDENTIALS_FILE
    (gitignored, same treatment as .spotify_token_cache/config.json) so later runs
    just load them -- no network call needed unless/until re-pairing is wanted.
    Registration has to succeed for construction to succeed: without a device_id,
    nothing else here works anyway, same as SpotifyOAuth's eager validation today.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = build_retrying_session()
        self.pairing_code: str | None = None

        if CREDENTIALS_FILE.exists():
            data = json.loads(CREDENTIALS_FILE.read_text())
            self.device_id: str = data["device_id"]
            self.device_secret: str = data["device_secret"]
            return

        self.device_secret = secrets.token_urlsafe(24)
        response = self.session.post(
            f"{self.base_url}/api/devices/register",
            json={"device_secret": self.device_secret},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        self.device_id = response.json()["device_id"]
        CREDENTIALS_FILE.write_text(json.dumps({"device_id": self.device_id, "device_secret": self.device_secret}))

        pairing = self._request("POST", f"/api/devices/{self.device_id}/pairing-code")
        self.pairing_code = pairing["code"]

    def _request(self, method: str, path: str, **kwargs):
        headers = {"Authorization": f"Bearer {self.device_secret}"}
        response = self.session.request(
            method, f"{self.base_url}{path}", headers=headers, timeout=DEFAULT_TIMEOUT, **kwargs
        )
        response.raise_for_status()
        return response.json()

    def get_config(self) -> BrokerConfig:
        json_data = self._request("GET", f"/api/devices/{self.device_id}/config")
        return BrokerConfig.model_validate(json_data)

    def get_current_track(self) -> dict[str, str] | None:
        """Same shape as the old SpotifyClient.get_current_track(): the broker
        refreshes and calls Spotify server-side, this device never sees a token."""
        return self._request("GET", f"/api/devices/{self.device_id}/now-playing")
