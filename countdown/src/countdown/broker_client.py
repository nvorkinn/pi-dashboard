import json
import secrets
from pathlib import Path

from countdown.abstract_client import AbstractClient
from countdown.config_manager import AppConfig
from countdown.http import DEFAULT_TIMEOUT
from display.pairing_code_panel import PairingCodePanel
from display.panel import Panel

CREDENTIALS_FILE = Path(".auth_broker_device")


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

    def _initialise(self) -> None:
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
        return

    def _request(self, method: str, path: str, **kwargs):
        headers = {"Authorization": f"Bearer {self.device_secret}"}
        response = self.session.request(
            method, f"{self.base_url}{path}", headers=headers, timeout=DEFAULT_TIMEOUT, **kwargs
        )
        response.raise_for_status()
        return response.json()

    def get_config(self) -> AppConfig:
        json_data = self._request("GET", f"/api/devices/{self.device_id}/config")
        return AppConfig.model_validate(json_data)

    def get_pairing_code_panel(self, config: AppConfig) -> PairingCodePanel:
        """Wraps an already-fetched BrokerConfig's pairing_code as a renderable
        panel -- doesn't fetch anything itself (get_config() already did, once,
        this cycle; no reason for a second round-trip just for this field) -- and
        uses the inherited cache to flag whether the code actually changed since
        the last time this was checked."""
        is_same = self._cache_and_compare("pairing_code", config.pairing_code)
        return PairingCodePanel(config.pairing_code, self.device_id, has_changed=not is_same)

    def _update(self) -> Panel | None:
        pass

    def fetch_app_config(self) -> tuple[AppConfig, PairingCodePanel]:
        """The device's config and current pairing status in one go, for the app's boot.
        Raises -- requests.exceptions.RequestException if the broker can't be reached,
        pydantic.ValidationError if it answers with something that isn't a complete config --
        rather than falling back to anything: with no valid config there's nothing sensible
        to run, so app.wait_for_config() shows a splash and retries."""
        config = self.get_config()
        return config, self.get_pairing_code_panel(config)
