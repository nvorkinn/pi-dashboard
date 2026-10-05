"""The device's name: what install.sh was given, as a slug. It ties this host's entities together in
Home Assistant (shared with pi-telemetry) and labels the device on the broker. Not the broker's
device_id, which a renderer gets when it registers."""

import os
import socket
import string

_DEVICE_NAME_CHARS = frozenset(string.ascii_lowercase + string.digits + "_-")


def _sanitize(raw: str) -> str:
    """Lowercases and replaces anything outside [a-z0-9_-] with '-', so the name is safe
    as an MQTT topic level and client id suffix (pi-telemetry's device_name.rs)."""
    chars = (c.lower() if c.isascii() else c for c in raw.strip())
    return "".join(c if c in _DEVICE_NAME_CHARS else "-" for c in chars)


def resolve_device_name(configured: str | None, hostname: str | None) -> str:
    """An explicit DEVICE_NAME wins, otherwise the hostname. Must resolve identically to
    pi-telemetry's, or the two end up as two separate HA devices."""
    if configured and configured.strip():
        source, raw = "DEVICE_NAME", configured
    elif hostname and hostname.strip():
        source, raw = "hostname", hostname
    else:
        raise ValueError("DEVICE_NAME is not set and the hostname could not be determined")

    device_name = _sanitize(raw)
    if all(c == "-" for c in device_name):
        raise ValueError(f"{source} {raw!r} has no usable characters for a device name")
    return device_name


def device_name_from_env() -> str:
    """DEVICE_NAME, or DEVICE_ID from an env file an older install.sh wrote, or else the hostname."""
    configured = next(
        (v for v in (os.environ.get("DEVICE_NAME"), os.environ.get("DEVICE_ID")) if v and v.strip()), None
    )
    return resolve_device_name(configured, socket.gethostname())
