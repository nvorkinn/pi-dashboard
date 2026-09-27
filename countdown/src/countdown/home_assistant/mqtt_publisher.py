import json
import logging
import os
import socket
import threading
from collections.abc import Mapping, Sequence

import paho.mqtt.client as mqtt

from countdown.core.abstract_client import AbstractClient, ClientStatus
from countdown.core.panel import Panel
from countdown.home_assistant.device_status import STAGES, DeviceStatus
from countdown.utils.device_id import resolve_device_id

logger = logging.getLogger(__name__)

# Shares pi-telemetry's HA device, but has its own discovery topic, state topic and client
# id: sharing any of those would have the two overwrite (or kick off) each other.

# Same as pi-telemetry: two missed one-minute publishes. Also covers a crash (no last will).
EXPIRE_AFTER_SECS = 180
CONNECT_TIMEOUT_SECS = 10
UNHEALTHY = frozenset({ClientStatus.ERROR, ClientStatus.FATAL})


def state_topic(device_id: str) -> str:
    return f"pi-telemetry/{device_id}/countdown/state"


def discovery_topic(device_id: str) -> str:
    return f"homeassistant/device/{device_id}_countdown/config"


def build_discovery_payload(device_id: str, api_names: Sequence[str]) -> str:
    """Device-based discovery message: one enum sensor per API (its ClientStatus), a "problem"
    binary sensor that's ON while any API is in ERROR or FATAL, and the device's stage,
    display connection and last broker sync."""

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
    components["stage"] = component(
        "sensor",
        "stage",
        "Stage",
        "{{ value_json.stage }}",
        device_class="enum",
        options=list(STAGES),
        entity_category="diagnostic",
    )
    components["display_connected"] = component(
        "binary_sensor",
        "display_connected",
        "Display connected",
        "{{ 'ON' if value_json.display_connected else 'OFF' }}",
        device_class="connectivity",
        entity_category="diagnostic",
    )
    components["last_broker_sync"] = component(
        "sensor",
        "last_broker_sync",
        "Last broker sync",
        "{{ value_json.last_broker_sync }}",
        device_class="timestamp",
        entity_category="diagnostic",
        availability_topic=state_topic(device_id),
        availability_template="{{ 'online' if value_json.last_broker_sync else 'offline' }}",
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
    """Reports the API clients' health and the device's stage to Home Assistant over MQTT.
    `clients` is the registry's own dict, so rebuilt clients are picked up automatically.
    Disabled when no broker host is configured."""

    def __init__(
        self,
        clients: Mapping[str, AbstractClient],
        api_names: Sequence[str],
        device_id: str,
        broker_host: str | None,
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
        status: DeviceStatus | None = None,
    ):
        super().__init__()
        self.clients = clients
        self.device_status = status or DeviceStatus()
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
    def from_env(
        cls, clients: Mapping[str, AbstractClient], api_names: Sequence[str], status: DeviceStatus | None = None
    ) -> MqttPublisher:
        """Same variables as pi-telemetry, but no localhost default: no host means disabled."""
        try:
            port = int(os.environ.get("MQTT_BROKER_PORT", ""))
        except ValueError:
            port = 1883
        broker_host = os.environ.get("MQTT_BROKER_HOST")
        if not broker_host:
            logger.info("MQTT: MQTT_BROKER_HOST is not set -- not reporting health to Home Assistant")
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
            status=status,
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
            client.connect(self.broker_host, self.port)
            client.loop_start()
            if not self._connected.wait(CONNECT_TIMEOUT_SECS):
                raise ConnectionError(f"MQTT broker at {self.broker_host}:{self.port} did not accept the connection")
        except Exception:
            self._teardown()
            raise

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            logger.error(f"MQTT broker refused the connection: {reason_code}")
            return
        self._connected.set()
        logger.info(f"MQTT: connected to {self.broker_host}:{self.port} as countdown-{self.device_id}")
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
        logger.warning(f"MQTT: disconnected from {self.broker_host}:{self.port} ({reason_code})")

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
        device = self.device_status
        return json.dumps(
            {
                **statuses,
                "problem": any(s in UNHEALTHY for s in statuses.values()),
                "stage": device.stage,
                "display_connected": device.display_connected,
                "last_broker_sync": device.last_broker_sync.isoformat() if device.last_broker_sync else None,
            }
        )

    def _update(self) -> Panel | None:
        """Raises if the connection has dropped, flagging ERROR so the next update()
        reconnects."""
        if self._client is None or not self._connected.is_set():
            self.status = ClientStatus.ERROR
            raise ConnectionError("Not connected to the MQTT broker")
        info = self._client.publish(state_topic(self.device_id), self.build_state_payload(), qos=1, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(f"MQTT publish failed: {mqtt.error_string(info.rc)}")
        return None
