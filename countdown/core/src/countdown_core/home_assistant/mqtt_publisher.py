import asyncio
import contextlib
import json
import logging
import os
import threading
from collections.abc import Mapping, Sequence

import paho.mqtt.client as mqtt

from countdown_core.core.abstract_client import AbstractClient, ClientStatus
from countdown_core.home_assistant.device_status import STAGES, DeviceStatus
from countdown_credentials.device_name import device_name_from_env

logger = logging.getLogger(__name__)

# Shares pi-telemetry's HA device, but has its own discovery topic, state topic and client
# id: sharing any of those would have the two overwrite (or kick off) each other.

# Same as pi-telemetry: once a minute, and expired after two missed publishes. Also covers a
# crash (no last will).
PUBLISH_INTERVAL_SECS = 60
EXPIRE_AFTER_SECS = 180
CONNECT_TIMEOUT_SECS = 10
UNHEALTHY = frozenset({ClientStatus.ERROR, ClientStatus.FATAL})


def state_topic(device_name: str) -> str:
    return f"pi-telemetry/{device_name}/countdown/state"


def discovery_topic(device_name: str) -> str:
    return f"homeassistant/device/{device_name}_countdown/config"


def build_discovery_payload(device_name: str, api_names: Sequence[str]) -> str:
    """Device-based discovery message: one enum sensor per API (its ClientStatus), a "problem"
    binary sensor that's ON while any API is in ERROR or FATAL, and the device's stage,
    display connection and last broker sync."""

    def component(platform: str, key: str, name: str, template: str, **extra: object) -> dict:
        return {
            "platform": platform,
            "unique_id": f"pi_telemetry_{device_name}_countdown_{key}",
            "name": name,
            "state_topic": state_topic(device_name),
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
        availability_topic=state_topic(device_name),
        availability_template="{{ 'online' if value_json.last_broker_sync else 'offline' }}",
    )
    return json.dumps(
        {
            # Same identifiers as pi-telemetry's device; only the fields both sides agree
            # on, so neither overwrites the other's.
            "device": {"identifiers": [f"pi_telemetry_{device_name}"], "name": device_name},
            "origin": {"name": "countdown"},
            "components": components,
        }
    )


class MqttPublisher:
    """Reports the API clients' health and the device's stage to Home Assistant over MQTT, from
    its own task (run()) so it does so from boot, while the device is still registering. Its
    settings come from the host, not the broker. `clients` is empty until ApiRegistry points it at
    its own dict, so rebuilt clients are picked up automatically. Disabled with no broker host."""

    def __init__(
        self,
        api_names: Sequence[str],
        device_name: str = "",
        broker_host: str | None = None,
        port: int = 1883,
        username: str | None = None,
        password: str | None = None,
        status: DeviceStatus | None = None,
    ):
        self.clients: Mapping[str, AbstractClient] = {}
        self.device_status = status or DeviceStatus()
        self.api_names = list(api_names)
        self.device_name = device_name
        self.broker_host = broker_host
        self.port = port
        self.username = username
        self.password = password
        self._client: mqtt.Client | None = None
        self._connected = threading.Event()
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None

    @classmethod
    def from_env(cls, api_names: Sequence[str], status: DeviceStatus | None = None) -> MqttPublisher:
        """Same variables as pi-telemetry, but no localhost default: no host means disabled."""
        try:
            port = int(os.environ.get("MQTT_BROKER_PORT", ""))
        except ValueError:
            port = 1883
        broker_host = os.environ.get("MQTT_BROKER_HOST")
        if not broker_host:
            logger.info("MQTT: MQTT_BROKER_HOST is not set -- not reporting health to Home Assistant")
        return cls(
            api_names,
            # Only resolved when there's a host to publish to: an unusable hostname must not
            # crash the app over a feature that's switched off.
            device_name=device_name_from_env() if broker_host else "",
            broker_host=broker_host,
            port=port,
            username=os.environ.get("MQTT_BROKER_USERNAME"),
            password=os.environ.get("MQTT_BROKER_PASSWORD"),
            status=status,
        )

    @property
    def enabled(self) -> bool:
        return bool(self.broker_host)

    def start(self) -> None:
        """Runs run() in the background, from inside the event loop. Holds on to the task, which
        asyncio itself only references weakly."""
        self._task = asyncio.create_task(self.run())

    async def run(self) -> None:
        """Publishes now, then every PUBLISH_INTERVAL_SECS or sooner if publish_soon() is called.
        Returns at once when disabled."""
        if not self.enabled:
            return
        while True:
            await self.publish()
            with contextlib.suppress(TimeoutError):  # the interval is up
                await asyncio.wait_for(self._wake.wait(), PUBLISH_INTERVAL_SECS)
            self._wake.clear()

    def publish_soon(self) -> None:
        """Has run() publish now rather than at the next interval, e.g. for a new stage."""
        self._wake.set()

    async def publish(self) -> bool:
        """One publish of the state, (re)connecting first if need be. Logged, never raised:
        telemetry must not cost the display anything."""
        try:
            await asyncio.to_thread(self._publish)
        except Exception as e:
            logger.warning(f"MQTT: couldn't publish health: {e}")
            self._teardown()  # so the next publish starts from a fresh connection
            return False
        return True

    def _publish(self) -> None:
        client = self._client if self._client is not None and self._connected.is_set() else self._connect()
        info = client.publish(state_topic(self.device_name), self.build_state_payload(), qos=1, retain=False)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(f"MQTT publish failed: {mqtt.error_string(info.rc)}")

    def _connect(self) -> mqtt.Client:
        self._teardown()
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"countdown-{self.device_name}")
        if self.username and self.password:
            client.username_pw_set(self.username, self.password)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        self._client = client
        client.connect(self.broker_host, self.port)
        client.loop_start()
        if not self._connected.wait(CONNECT_TIMEOUT_SECS):
            raise ConnectionError(f"MQTT broker at {self.broker_host}:{self.port} did not accept the connection")
        return client

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            logger.error(f"MQTT broker refused the connection: {reason_code}")
            return
        self._connected.set()
        logger.info(f"MQTT: connected to {self.broker_host}:{self.port} as countdown-{self.device_name}")
        # Retained so HA picks the device up after its own restart, and re-sent on every
        # (re)connect so it self-heals if the broker's store is wiped.
        client.publish(
            discovery_topic(self.device_name),
            build_discovery_payload(self.device_name, self.api_names),
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
