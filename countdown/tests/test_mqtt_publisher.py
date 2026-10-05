import asyncio
import json
import logging
from datetime import UTC, datetime
from types import SimpleNamespace

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode
from test_utils import REGISTRATION

from countdown_core.core.abstract_client import AbstractClient, ClientStatus
from countdown_core.home_assistant import mqtt_publisher
from countdown_core.home_assistant.device_status import STAGES, DeviceStatus
from countdown_core.home_assistant.mqtt_publisher import (
    MqttPublisher,
    build_discovery_payload,
    discovery_topic,
    state_topic,
)
from countdown_credentials import device_name

API_NAMES = ["glowmarkt", "tfl"]
DEVICE_DEFAULTS = {"stage": "waiting_for_broker", "display_connected": False, "last_broker_sync": None}
STATE_TOPIC = "pi-telemetry/sister-hat/countdown/state"


class FakeMqttClient:
    """Records what the publisher does. loop_start() stands in for the network thread
    delivering the broker's CONNACK, per `connack_identifier` (0 = accepted)."""

    instances: list[FakeMqttClient] = []
    connack_identifier: int | None = 0
    publish_rc = mqtt.MQTT_ERR_SUCCESS

    def __init__(self, callback_api_version, client_id=None):
        self.client_id = client_id
        self.credentials = None
        self.address = None
        self.published: list[dict] = []
        self.on_connect = self.on_disconnect = None
        self.stopped = False
        FakeMqttClient.instances.append(self)

    def username_pw_set(self, username, password):
        self.credentials = (username, password)

    def connect(self, host, port):
        self.address = (host, port)

    def loop_start(self):
        if self.connack_identifier is not None:
            self.on_connect(self, None, {}, ReasonCode(PacketTypes.CONNACK, identifier=self.connack_identifier), None)

    def loop_stop(self):
        self.stopped = True

    def disconnect(self):
        pass

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append({"topic": topic, "payload": json.loads(payload), "qos": qos, "retain": retain})
        return SimpleNamespace(rc=self.publish_rc)

    def drop_connection(self):
        self.on_disconnect(self, None, None, ReasonCode(PacketTypes.DISCONNECT, identifier=0), None)


class StubClient(AbstractClient):
    def __init__(self, status: ClientStatus):
        super().__init__(REGISTRATION)
        self.status = status

    def _initialise(self) -> None:
        pass

    def _update(self):
        pass


@pytest.fixture(autouse=True)
def fake_paho(monkeypatch):
    FakeMqttClient.instances = []
    FakeMqttClient.connack_identifier = 0
    FakeMqttClient.publish_rc = mqtt.MQTT_ERR_SUCCESS
    monkeypatch.setattr(mqtt_publisher.mqtt, "Client", FakeMqttClient)
    monkeypatch.setattr(mqtt_publisher, "CONNECT_TIMEOUT_SECS", 0.01)


def publisher(clients=None, host: str | None = "broker.local", **kwargs) -> MqttPublisher:
    pub = MqttPublisher(API_NAMES, device_name="sister-hat", broker_host=host, **kwargs)
    if clients is not None:
        pub.clients = clients
    return pub


def states() -> list[dict]:
    """Every state message published, across reconnects."""
    return [m for fake in FakeMqttClient.instances for m in fake.published if m["topic"] == STATE_TOPIC]


async def until(condition, timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.001)


async def run_briefly(pub: MqttPublisher, condition) -> None:
    """Runs pub.run() until `condition` holds, then stops it."""
    task = asyncio.create_task(pub.run())
    try:
        await until(condition)
    finally:
        task.cancel()


# --- topics and discovery: must sit beside pi-telemetry's, not on top of it ----------


def test_topics_are_siblings_of_pi_telemetrys_never_the_same():
    assert state_topic("sister-hat") == "pi-telemetry/sister-hat/countdown/state"
    assert state_topic("sister-hat") != "pi-telemetry/sister-hat/state"
    assert discovery_topic("sister-hat") == "homeassistant/device/sister-hat_countdown/config"
    assert discovery_topic("sister-hat") != "homeassistant/device/sister-hat/config"


def test_discovery_joins_pi_telemetrys_ha_device():
    payload = json.loads(build_discovery_payload("sister-hat", API_NAMES))

    assert payload["device"]["identifiers"] == ["pi_telemetry_sister-hat"]
    assert payload["device"]["name"] == "sister-hat"


def test_discovery_has_a_status_sensor_per_api_and_a_problem_binary_sensor():
    components = json.loads(build_discovery_payload("sister-hat", API_NAMES))["components"]

    assert set(components) == {"glowmarkt", "tfl", "problem", "stage", "display_connected", "last_broker_sync"}
    assert components["tfl"]["platform"] == "sensor"
    assert components["tfl"]["device_class"] == "enum"
    assert components["tfl"]["options"] == [s.value for s in ClientStatus]
    assert components["tfl"]["value_template"] == "{{ value_json.tfl }}"
    assert components["problem"]["platform"] == "binary_sensor"
    assert components["problem"]["device_class"] == "problem"


def test_every_component_reads_the_state_topic_and_expires():
    components = json.loads(build_discovery_payload("sister-hat", API_NAMES))["components"].values()

    assert {c["state_topic"] for c in components} == {STATE_TOPIC}
    assert {c["expire_after"] for c in components} == {180}


def test_unique_ids_are_distinct_per_host_and_metric():
    def unique_ids(name):
        components = json.loads(build_discovery_payload(name, API_NAMES))["components"]
        return [c["unique_id"] for c in components.values()]

    a, b = unique_ids("host-a"), unique_ids("host-b")

    assert len(set(a)) == len(a)
    assert not set(a) & set(b)


def test_discovery_describes_the_stage_display_and_sync_sensors():
    components = json.loads(build_discovery_payload("sister-hat", API_NAMES))["components"]

    stage = components["stage"]
    assert (stage["platform"], stage["device_class"], stage["options"]) == ("sensor", "enum", list(STAGES))
    assert stage["value_template"] == "{{ value_json.stage }}"
    display = components["display_connected"]
    assert (display["platform"], display["device_class"]) == ("binary_sensor", "connectivity")
    sync = components["last_broker_sync"]
    assert (sync["platform"], sync["device_class"]) == ("sensor", "timestamp")
    # Unavailable until the first sync, instead of a template error on a null timestamp.
    assert sync["availability_topic"] == sync["state_topic"]
    assert "online" in sync["availability_template"]


# --- state payload -------------------------------------------------------------------


def test_before_there_are_any_clients_every_api_reads_as_disabled_while_waiting_for_the_broker():
    pub = publisher()

    assert pub.clients == {}
    assert json.loads(pub.build_state_payload()) == {
        "glowmarkt": "disabled",
        "tfl": "disabled",
        "problem": False,
        **DEVICE_DEFAULTS,
    }


def test_state_payload_reports_each_clients_status():
    pub = publisher({"glowmarkt": StubClient(ClientStatus.CONNECTED), "tfl": StubClient(ClientStatus.UNINITIALISED)})

    assert json.loads(pub.build_state_payload()) == {
        "glowmarkt": "connected",
        "tfl": "uninitialised",
        "problem": False,
        **DEVICE_DEFAULTS,
    }


def test_an_api_with_no_client_reads_as_disabled():
    pub = publisher({"tfl": StubClient(ClientStatus.CONNECTED)})

    assert json.loads(pub.build_state_payload())["glowmarkt"] == "disabled"


@pytest.mark.parametrize("status", [ClientStatus.ERROR, ClientStatus.FATAL])
def test_problem_is_set_while_any_api_is_in_error(status):
    pub = publisher({"glowmarkt": StubClient(ClientStatus.CONNECTED), "tfl": StubClient(status)})

    assert json.loads(pub.build_state_payload())["problem"] is True


def test_state_follows_the_clients_as_they_change():
    tfl = StubClient(ClientStatus.CONNECTED)
    pub = publisher({"tfl": tfl})
    assert json.loads(pub.build_state_payload())["problem"] is False

    tfl.status = ClientStatus.ERROR

    assert json.loads(pub.build_state_payload())["problem"] is True


def test_the_state_payload_carries_the_devices_stage_display_and_last_sync():
    synced = datetime(2026, 9, 20, 10, 30, tzinfo=UTC)
    status = DeviceStatus(stage="setup", last_broker_sync=synced, display=SimpleNamespace(panel_connected=True))

    payload = json.loads(publisher(status=status).build_state_payload())

    assert payload["stage"] == "setup"
    assert payload["display_connected"] is True
    assert payload["last_broker_sync"] == "2026-09-20T10:30:00+00:00"


@pytest.mark.parametrize("panel_connected", [None, False])
def test_a_display_that_is_unknown_or_absent_is_not_reported_as_connected(panel_connected):
    status = DeviceStatus(display=SimpleNamespace(panel_connected=panel_connected))

    assert json.loads(publisher(status=status).build_state_payload())["display_connected"] is False


def test_with_no_display_at_all_it_is_not_connected():
    assert DeviceStatus().display_connected is False


# --- publishing ----------------------------------------------------------------------


def test_publish_connects_announces_the_device_retained_then_publishes_the_state():
    pub = publisher({"tfl": StubClient(ClientStatus.ERROR)}, username="ha", password="secret", port=1884)

    assert asyncio.run(pub.publish()) is True

    (fake,) = FakeMqttClient.instances
    assert fake.address == ("broker.local", 1884)
    assert fake.credentials == ("ha", "secret")
    assert fake.client_id == "countdown-sister-hat"  # pi-telemetry's is "pi-telemetry-<name>"
    discovery, state = fake.published
    assert (discovery["topic"], discovery["qos"], discovery["retain"]) == (
        "homeassistant/device/sister-hat_countdown/config",
        1,
        True,
    )
    assert (state["topic"], state["qos"], state["retain"]) == (STATE_TOPIC, 1, False)
    assert state["payload"] == {"glowmarkt": "disabled", "tfl": "error", "problem": True, **DEVICE_DEFAULTS}


def test_a_later_publish_reuses_the_connection():
    pub = publisher()

    asyncio.run(pub.publish())
    asyncio.run(pub.publish())

    assert len(FakeMqttClient.instances) == 1
    assert len(states()) == 2


def test_a_refused_connection_is_logged_not_raised_and_torn_down(caplog):
    FakeMqttClient.connack_identifier = 135  # not authorised
    pub = publisher()

    assert asyncio.run(pub.publish()) is False

    assert "MQTT: couldn't publish health" in caplog.text
    assert FakeMqttClient.instances[0].stopped
    assert states() == []


def test_an_unreachable_broker_is_logged_not_raised(monkeypatch, caplog):
    def unreachable(self, host, port):
        raise OSError("no route")

    monkeypatch.setattr(FakeMqttClient, "connect", unreachable)

    assert asyncio.run(publisher().publish()) is False
    assert "no route" in caplog.text


def test_a_dropped_connection_is_reconnected_by_the_next_publish():
    pub = publisher()
    asyncio.run(pub.publish())
    FakeMqttClient.instances[0].drop_connection()

    assert asyncio.run(pub.publish()) is True

    assert len(FakeMqttClient.instances) == 2
    assert FakeMqttClient.instances[0].stopped  # the old network loop is torn down, not leaked
    assert FakeMqttClient.instances[1].published[-1]["topic"] == STATE_TOPIC


def test_a_failed_publish_reconnects_next_time():
    pub = publisher()
    FakeMqttClient.publish_rc = mqtt.MQTT_ERR_NO_CONN

    assert asyncio.run(pub.publish()) is False

    FakeMqttClient.publish_rc = mqtt.MQTT_ERR_SUCCESS
    assert asyncio.run(pub.publish()) is True
    assert len(FakeMqttClient.instances) == 2


def test_it_logs_where_it_connected_and_when_the_connection_drops(caplog):
    caplog.set_level(logging.INFO)

    asyncio.run(publisher(port=1884).publish())
    assert "MQTT: connected to broker.local:1884 as countdown-sister-hat" in caplog.text

    FakeMqttClient.instances[0].drop_connection()
    assert "MQTT: disconnected from broker.local:1884" in caplog.text


# --- running in the background -------------------------------------------------------


def test_run_publishes_at_once_and_then_every_interval(monkeypatch):
    monkeypatch.setattr(mqtt_publisher, "PUBLISH_INTERVAL_SECS", 0.01)

    asyncio.run(run_briefly(publisher(), lambda: len(states()) >= 3))

    assert len(FakeMqttClient.instances) == 1  # one connection for all of them


def test_publish_soon_wakes_run_before_the_interval_is_up():
    pub = publisher()  # the real one-minute interval

    async def scenario():
        task = asyncio.create_task(pub.run())
        try:
            await until(lambda: len(states()) == 1)
            pub.publish_soon()
            await until(lambda: len(states()) == 2)
        finally:
            task.cancel()

    asyncio.run(scenario())


def test_run_keeps_going_after_a_failed_publish(monkeypatch):
    monkeypatch.setattr(mqtt_publisher, "PUBLISH_INTERVAL_SECS", 0.01)
    FakeMqttClient.connack_identifier = 135

    async def scenario():
        task = asyncio.create_task(pub.run())
        try:
            await until(lambda: len(FakeMqttClient.instances) == 2)  # retried, still refused
            FakeMqttClient.connack_identifier = 0
            await until(lambda: len(states()) >= 1)
        finally:
            task.cancel()

    pub = publisher()
    asyncio.run(scenario())


def test_start_runs_it_in_the_background():
    pub = publisher()

    async def scenario():
        pub.start()
        await until(lambda: len(states()) == 1)
        pub._task.cancel()

    asyncio.run(scenario())


def test_without_a_broker_host_run_returns_at_once_and_never_connects():
    pub = publisher(host=None)

    asyncio.run(asyncio.wait_for(pub.run(), 1))

    assert not pub.enabled
    assert FakeMqttClient.instances == []


# --- from the environment ------------------------------------------------------------


def test_from_env_reads_the_same_variables_as_pi_telemetry(monkeypatch):
    monkeypatch.setenv("MQTT_BROKER_HOST", "192.168.0.181")
    monkeypatch.setenv("MQTT_BROKER_PORT", "1885")
    monkeypatch.setenv("MQTT_BROKER_USERNAME", "ha")
    monkeypatch.setenv("MQTT_BROKER_PASSWORD", "secret")
    monkeypatch.setenv("DEVICE_NAME", "Sister HAT")
    status = DeviceStatus()

    pub = MqttPublisher.from_env(API_NAMES, status)

    assert (pub.broker_host, pub.port, pub.username, pub.password) == ("192.168.0.181", 1885, "ha", "secret")
    assert pub.device_name == "sister-hat"
    assert pub.device_status is status
    assert pub.api_names == API_NAMES


def test_from_env_is_disabled_with_no_host_and_falls_back_to_the_default_port(monkeypatch):
    monkeypatch.setenv("MQTT_BROKER_PORT", "not-a-port")

    pub = MqttPublisher.from_env(API_NAMES)

    assert not pub.enabled
    assert pub.port == 1883


def test_from_env_never_needs_a_device_name_while_disabled(monkeypatch):
    monkeypatch.setattr(device_name.socket, "gethostname", lambda: "")

    assert not MqttPublisher.from_env(API_NAMES).enabled

    monkeypatch.setenv("MQTT_BROKER_HOST", "broker.local")
    with pytest.raises(ValueError):
        MqttPublisher.from_env(API_NAMES)


def test_it_says_so_when_it_is_switched_off(caplog):
    caplog.set_level(logging.INFO)
    MqttPublisher.from_env(API_NAMES)

    assert "MQTT_BROKER_HOST is not set" in caplog.text


def test_it_stays_quiet_about_being_off_when_a_host_is_set(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("MQTT_BROKER_HOST", "broker.local")

    MqttPublisher.from_env(API_NAMES)

    assert "not set" not in caplog.text
