"""Hands the device's credentials to Fluent Bit, which ships the host's logs and metrics. Called by a
standalone Pi once the broker has taken the registration, so Fluent Bit never starts (and never sends a
rejected token) before then. A renderer for a separate screen (countdown-server) doesn't: its host already runs
Fluent Bit, and the app only sends its OTLP metrics to it.

The env file is Fluent Bit's `EnvironmentFile=`, and its unit only runs once it exists (see
systemd/fluent-bit-env.conf at the repo root). A systemd path unit starts it on the first write and
restarts it when the secret changes; later boots start it by themselves. Without FLUENT_BIT_ENV_FILE (a
container, a dev machine) there's nothing to do."""

import logging
import os

from countdown_credentials.device_name import device_name_from_env

logger = logging.getLogger(__name__)

ENV_FILE_VAR = "FLUENT_BIT_ENV_FILE"


def _owner_only(path: str, flags: int) -> int:
    return os.open(path, flags, 0o600)


def enable_log_shipping(device_secret: str) -> None:
    """Writes the secret (as the bearer token) and the device name where Fluent Bit reads them. Never
    raises: shipping logs must not stop the device from registering."""
    path = os.environ.get(ENV_FILE_VAR)
    if not path:
        return
    try:
        device_name = device_name_from_env()
    except ValueError:
        device_name = "unknown"
    content = f"FLUENT_BIT_TOKEN={device_secret}\nDEVICE_NAME={device_name}\n"
    try:
        if os.path.exists(path):
            with open(path) as file:
                if file.read() == content:
                    return  # unchanged, so the path unit doesn't restart Fluent Bit on every boot
        # In place, not renamed over, which is what the path unit watches for.
        with open(path, "w", opener=_owner_only) as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(content)
        logger.info("Registered: Fluent Bit can now ship this device's logs and metrics")
    except OSError as e:
        logger.warning("Couldn't write %s, so logs and metrics won't be shipped: %s", path, e)
