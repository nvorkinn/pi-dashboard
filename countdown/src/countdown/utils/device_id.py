import string

_DEVICE_ID_CHARS = frozenset(string.ascii_lowercase + string.digits + "_-")


def _sanitize(raw: str) -> str:
    """Lowercases and replaces anything outside [a-z0-9_-] with '-', so the id is safe
    as an MQTT topic level and client id suffix (pi-telemetry's device_id.rs)."""
    chars = (c.lower() if c.isascii() else c for c in raw.strip())
    return "".join(c if c in _DEVICE_ID_CHARS else "-" for c in chars)


def resolve_device_id(configured: str | None, hostname: str | None) -> str:
    """The id that ties this host's entities together in HA: an explicit DEVICE_ID wins,
    otherwise the hostname. Must resolve identically to pi-telemetry's, or the two
    end up as two separate HA devices."""
    if configured and configured.strip():
        source, raw = "DEVICE_ID", configured
    elif hostname and hostname.strip():
        source, raw = "hostname", hostname
    else:
        raise ValueError("DEVICE_ID is not set and the hostname could not be determined")

    device_id = _sanitize(raw)
    if all(c == "-" for c in device_id):
        raise ValueError(f"{source} {raw!r} has no usable characters for a device id")
    return device_id
