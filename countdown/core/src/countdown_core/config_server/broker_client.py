import json
import os
import secrets
import socket
from pathlib import Path

from countdown_core.config_server.models import AppConfig
from countdown_core.core.abstract_client import DEFAULT_TIMEOUT, AbstractClient
from countdown_core.core.panel import Panel
from countdown_core.system_screens.pairing_code_panel import PairingCodePanel
from countdown_core.utils.device_id import resolve_device_id

CREDENTIALS_FILE = Path(".auth_broker_device")


def _device_name_header() -> dict[str, str]:
    """X-Device-Name is cosmetic on the broker side, so it's sent on every call (a rename
    shows on the next poll) but never allowed to fail a request."""
    try:
        return {"X-Device-Name": resolve_device_id(os.environ.get("DEVICE_ID"), socket.gethostname())}
    except ValueError:
        return {}


class BrokerClient(AbstractClient):
    """Talks to auth-broker (https://github.com/nvorkinn/auth-broker). Registers on first
    run and persists the credentials to CREDENTIALS_FILE, so later runs just load them."""

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
        headers = {"Authorization": f"Bearer {self.device_secret}", **_device_name_header()}
        response = self.session.request(
            method, f"{self.base_url}{path}", headers=headers, timeout=DEFAULT_TIMEOUT, **kwargs
        )
        response.raise_for_status()
        return response.json()

    def get_config(self) -> AppConfig:
        json_data = self._request("GET", f"/api/devices/{self.device_id}/config")
        return AppConfig.model_validate(json_data)

    def get_pairing_code_panel(self, config: AppConfig) -> PairingCodePanel:
        """Wraps the config's pairing_code as a panel, flagging whether it changed since
        the last check."""
        is_same = self._cache_and_compare("pairing_code", config.pairing_code)
        return PairingCodePanel(config.pairing_code, self.device_id, has_changed=not is_same)

    def _update(self) -> Panel | None:
        pass

    def fetch_app_config(self) -> tuple[AppConfig, PairingCodePanel]:
        """The config and pairing status in one go, for boot. Raises rather than falling
        back if the broker can't be reached or the config is invalid."""
        config = self.get_config()
        return config, self.get_pairing_code_panel(config)
