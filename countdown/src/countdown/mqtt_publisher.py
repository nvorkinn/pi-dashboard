import json
import os
import socket
import string
import threading
from collections.abc import Mapping, Sequence

import paho.mqtt.client as mqtt

from countdown.abstract_client import AbstractClient, ClientStatus
from display.panel import Panel

# Topic, discovery and payload conventions follow pi-telemetry
# (https://github.com/nvorkinn/pi-telemetry), the Rust sidecar that reports the Pi's
# system metrics to Home Assistant. Both processes describe the *same* HA device (same
# `device.identifiers`), so the API health entities show up next to the CPU/memory ones,
# but each has its own discovery topic, state topic and MQTT client id -- sharing any of
# those would have the two overwrite (or kick off) each other.

# Entities go `unavailable` in HA if no state arrives for this long: pi-telemetry's value,
# tolerating two missed one-minute publishes. Also what covers a crash, since
# there's no last-will message.
EXPIRE_AFTER_SECS = 180
CONNECT_TIMEOUT_SECS = 10
UNHEALTHY = frozenset({ClientStatus.ERROR, ClientStatus.FATAL})

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


def state_topic(device_id: str) -> str:
    return f"pi-telemetry/{device_id}/countdown/state"


def discovery_topic(device_id: str) -> str:
    return f"homeassistant/device/{device_id}_countdown/config"


def build_discovery_payload(device_id: str, api_names: Sequence[str]) -> str:
    """Device-based discovery message: one enum sensor per API (its ClientStatus) and a
    single "problem" binary sensor that's ON while any API is in ERROR or FATAL."""

    def component(platform: str, key: str, name: str, template: str, **extra: object) -> dict:
        return {
            "platform": platform,
            "unique_id": f"pi_telemetry_{device_id}_countdown_{key}",
            "name": name,
            "state_topic": state_topic(device_id),
            "value_template": template,
            "expire_after": EXPIRE_AFTER_SECS,
            **extra,
        }

    components = {
        name: component(
            "sensor",
            name,
            f"{name.replace('_', ' ').capitalize()} status",
            f"{{{{ value_json.{name} }}}}",
            device_class="enum",
            options=[status.value for status in ClientStatus],
            entity_category="diagnostic",
        )
        for name in api_names
    }
    components["problem"] = component(
        "binary_sensor",
        "problem",
        "API problem",
        "{{ 'ON' if value_json.problem else 'OFF' }}",
        device_class="problem",
    )
    return json.dumps(
        {
            # Same identifiers as pi-telemetry's device; only the fields both sides agree
            # on, so neither overwrites the other's.
            "device": {"identifiers": [f"pi_telemetry_{device_id}"], "name": device_id},
            "origin": {"name": "countdown"},
            "components": components,
        }
    )


class MqttPublisher(AbstractClient):
    """Reports the other API clients' health to Home Assistant over MQTT. Unlike them
    it has no panel: initialise() connects (and announces itself via a retained HA
    discovery message), and each _update() publishes one JSON state message holding
    every API's ClientStatus, read straight off `clients` -- the registry's own dict,
    so a client that's dropped or rebuilt is reflected without telling this class. An
    API with no client (switched off in config) reads as DISABLED.

    Disabled itself (no calls, ever) when no broker host is configured, so a dev machine
    or a Pi without Home Assistant just doesn't publish. paho's network thread handles
    keepalive and reconnects on its own; _update() only checks the connection is up."""

    def __init__(
        self,
        clients: Mapping[str, AbstractClient],
        api_names: Sequence[str],
        device_id: str,
        broker_host: str | None,
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
    ):
        super().__init__()
        self.clients = clients
        self.api_names = list(api_names)
        self.device_id = device_id
        self.broker_host = broker_host
        self.port = port
        self.username = username
        self.password = password
        self._client: mqtt.Client | None = None
        self._connected = threading.Event()
        if not broker_host:
            self.status = ClientStatus.DISABLED

    @classmethod
    def from_env(cls, clients: Mapping[str, AbstractClient], api_names: Sequence[str]) -> MqttPublisher:
        """Same variables as pi-telemetry, so both can share one systemd env file. Unlike
        pi-telemetry there's no localhost default for the host: unset means disabled."""
        try:
            port = int(os.environ.get("MQTT_BROKER_PORT", ""))
        except ValueError:
            port = 1883
        broker_host = os.environ.get("MQTT_BROKER_HOST")
        if not broker_host:
            print("MQTT: MQTT_BROKER_HOST is not set -- not reporting health to Home Assistant")
        # Only resolved when there's a host to publish to: an unusable hostname must not
        # crash the app over a feature that's switched off.
        device_id = resolve_device_id(os.environ.get("DEVICE_ID"), socket.gethostname()) if broker_host else ""
        return cls(
            clients,
            api_names,
            device_id=device_id,
            broker_host=broker_host,
            port=port,
            username=os.environ.get("MQTT_BROKER_USERNAME"),
            password=os.environ.get("MQTT_BROKER_PASSWORD"),
        )

    def _initialise(self) -> None:
        self._teardown()
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"countdown-{self.device_id}")
        if self.username and self.password:
            client.username_pw_set(self.username, self.password)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        self._client = client
        try:
            # Blocks (DNS, TCP, then the broker's CONNACK) -- fine, we're in a worker thread.
            client.connect(self.broker_host, self.port)
            client.loop_start()
            if not self._connected.wait(CONNECT_TIMEOUT_SECS):
                raise ConnectionError(f"MQTT broker at {self.broker_host}:{self.port} did not accept the connection")
        except Exception:
            self._teardown()
            raise

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            print(f"MQTT broker refused the connection: {reason_code}")
            return
        self._connected.set()
        print(f"MQTT: connected to {self.broker_host}:{self.port} as countdown-{self.device_id}")
        # Retained so HA picks the device up after its own restart, and re-sent on every
        # (re)connect so it self-heals if the broker's store is wiped.
        client.publish(
            discovery_topic(self.device_id),
            build_discovery_payload(self.device_id, self.api_names),
            qos=1,
            retain=True,
        )

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        self._connected.clear()
        print(f"MQTT: disconnected from {self.broker_host}:{self.port} ({reason_code})")

    def _teardown(self) -> None:
        if self._client is not None:
            self._client.disconnect()
            self._client.loop_stop()
            self._client = None
        self._connected.clear()

    def build_state_payload(self) -> str:
        statuses = {
            name: self.clients[name].status if name in self.clients else ClientStatus.DISABLED
            for name in self.api_names
        }
        return json.dumps({**statuses, "problem": any(s in UNHEALTHY for s in statuses.values())})

    def _update(self) -> Panel | None:
        """Raises if the connection has dropped, flagging ERROR so the next update()
        rebuilds it rather than trusting a CONNECTED status that's no longer true."""
        if self._client is None or not self._connected.is_set():
            self.status = ClientStatus.ERROR
            raise ConnectionError("Not connected to the MQTT broker")
        info = self._client.publish(state_topic(self.device_id), self.build_state_payload(), qos=1, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(f"MQTT publish failed: {mqtt.error_string(info.rc)}")
        return None
