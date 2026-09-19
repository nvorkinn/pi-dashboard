import json
import os
from pathlib import Path

from countdown.abstract_client import AbstractClient
from countdown.config_manager import SpotifyConfig
from countdown.http import DEFAULT_TIMEOUT
from countdown.models import SpotifyPlayingRightNow
from display.panel import Panel
from display.spotify_panel import SpotifyPanel

CREDENTIALS_FILE = Path(".auth_broker_device")


class SpotifyClient(AbstractClient):
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

    def __init__(self, config: SpotifyConfig):
        super().__init__(config)
        self.base_url = os.environ["BROKER_URL"]
        if CREDENTIALS_FILE.exists():
            data = json.loads(CREDENTIALS_FILE.read_text())
            self.device_id: str = data["device_id"]
            self.device_secret: str = data["device_secret"]

    def _initialise(self) -> None:
        pass

    def _request(self, method: str, path: str, **kwargs):
        headers = {"Authorization": f"Bearer {self.device_secret}"}
        response = self.session.request(
            method, f"{self.base_url}{path}", headers=headers, timeout=DEFAULT_TIMEOUT, **kwargs
        )
        response.raise_for_status()
        return response.json()

    def _update(self) -> Panel | None:
        """Same shape as the old SpotifyClient.get_current_track(): the broker
        refreshes and calls Spotify server-side, this device never sees a token."""
        json = self._request("GET", f"/api/devices/{self.device_id}/now-playing")
        if json is None:
            return None
        return SpotifyPanel(SpotifyPlayingRightNow.model_validate(json))
