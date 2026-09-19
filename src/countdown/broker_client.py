import json
import secrets
from pathlib import Path

import pydantic
import requests

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

    async def initialise(self) -> None:
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

    async def _update(self) -> Panel | None:
        pass

    def fetch_app_config(self) -> tuple[AppConfig, PairingCodePanel]:
        """Tries once to get real config (and current pairing status) before
        DisplayLoop is constructed, so it never has to build a TflClient/
        WeatherClient/GlowClient from a config it already knows is empty. Falls back
        to AppConfig()'s empty defaults and a no-code PairingCodePanel if the
        broker's unreachable at boot (e.g. network not up yet) -- the same
        graceful-degrade safe_fetch provides everywhere else, not a retry loop that
        would block startup indefinitely. No code in that fallback means "proceed
        as normal", not "definitely paired" -- if we can't reach the broker we
        don't actually know either way, and showing a stale/unverifiable code would
        be worse than just falling through to the ordinary (empty) display. This
        one case bypasses BrokerClient's own cache entirely (via has_changed=False
        directly, not get_pairing_code_panel()) since there's nothing to compare
        against yet -- no fetch happened at all."""
        try:
            config = self.get_config()
            return config, self.get_pairing_code_panel(config)
        except requests.exceptions.RequestException as e:
            print(f"Exception with API call to the broker: {e}")
        except pydantic.ValidationError as e:
            print(f"Pydantic validation error: {e}")
        return AppConfig(), PairingCodePanel(None, self.device_id, has_changed=False)
