import json
import secrets
from pathlib import Path

from pydantic import BaseModel

from countdown.abstract_client import AbstractClient
from countdown.http import DEFAULT_TIMEOUT
from display.pairing_code_panel import PairingCodePanel

CREDENTIALS_FILE = Path(".auth_broker_device")


class BrokerTflConfig(BaseModel):
    app_key: str
    stop_ids: list[str]


class BrokerWeatherConfig(BaseModel):
    api_key: str
    location: str


class BrokerSpotifyConfig(BaseModel):
    enabled: bool


class BrokerGlowmarktConfig(BaseModel):
    # None, not "" -- the broker sends null when a device's owner hasn't set up
    # Glowmarkt (the common case for most gifted devices).
    username: str | None
    password: str | None


class BrokerConfig(BaseModel):
    interval: int
    tfl: BrokerTflConfig
    weather: BrokerWeatherConfig
    spotify: BrokerSpotifyConfig
    glowmarkt: BrokerGlowmarktConfig
    # Non-null exactly while this device hasn't been paired with a recipient yet
    # (the server tracks that durably, not just "has an active pairing code" --
    # a code can expire and get regenerated without the device ever un-pairing).
    # Checked/displayed every cycle via DisplayLoop.refresh_broker_config(), not
    # requested once at registration -- a code generated once at boot could sit
    # unseen and expire long before a gifted device's recipient gets around to
    # unboxing it.
    pairing_code: str | None


class BrokerClient(AbstractClient):
    """Talks to auth-broker (https://github.com/nvorkinn/auth-broker), the cloud
    service that handles Spotify OAuth and hosts this device's config centrally --
    gifted frames have no stable public address of their own, so the broker is the
    one place that needs real TLS.

    Registers itself on first run, persisting credentials to CREDENTIALS_FILE
    (gitignored, same treatment as .spotify_token_cache/config.json) so later runs
    just load them -- no network call needed at all once registered. Registration
    has to succeed for construction to succeed: without a device_id, nothing else
    here works anyway, same as SpotifyOAuth's eager validation today.

    Deliberately doesn't request a pairing code itself -- that's part of
    get_config()'s response (see BrokerConfig.pairing_code), checked fresh every
    cycle by the caller, not a one-time thing this class owns.
    """

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url.rstrip("/")

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

    def get_pairing_code_panel(self, config: BrokerConfig) -> PairingCodePanel:
        """Wraps an already-fetched BrokerConfig's pairing_code as a renderable
        panel -- doesn't fetch anything itself (get_config() already did, once,
        this cycle; no reason for a second round-trip just for this field) -- and
        uses the inherited cache to flag whether the code actually changed since
        the last time this was checked."""
        is_same = self._cache_and_compare("pairing_code", config.pairing_code)
        return PairingCodePanel(config.pairing_code, self.device_id, has_changed=not is_same)

    def get_current_track(self) -> dict[str, str] | None:
        """Same shape as the old SpotifyClient.get_current_track(): the broker
        refreshes and calls Spotify server-side, this device never sees a token."""
        return self._request("GET", f"/api/devices/{self.device_id}/now-playing")
