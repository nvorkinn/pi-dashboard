import asyncio
import json
from types import SimpleNamespace

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode

from countdown import mqtt_publisher
from countdown.abstract_client import AbstractClient, ClientStatus
from countdown.mqtt_publisher import (
    MqttPublisher,
    build_discovery_payload,
    discovery_topic,
    resolve_device_id,
    state_topic,
)

API_NAMES = ["glowmarkt", "tfl"]


class FakeMqttClient:
    """Records what the publisher does. loop_start() stands in for the network thread
    delivering the broker's CONNACK, per `connack_identifier` (0 = accepted)."""

    instances: list[FakeMqttClient] = []
    connack_identifier: int | None = 0

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
        return SimpleNamespace(rc=mqtt.MQTT_ERR_SUCCESS)

    def drop_connection(self):
        self.on_disconnect(self, None, None, ReasonCode(PacketTypes.DISCONNECT, identifier=0), None)


class StubClient(AbstractClient):
    def __init__(self, status: ClientStatus):
        super().__init__()
        self.status = status

    def _initialise(self) -> None:
        pass

    def _update(self):
        pass


@pytest.fixture(autouse=True)
def fake_paho(monkeypatch):
    FakeMqttClient.instances = []
    FakeMqttClient.connack_identifier = 0
    monkeypatch.setattr(mqtt_publisher.mqtt, "Client", FakeMqttClient)
    monkeypatch.setattr(mqtt_publisher, "CONNECT_TIMEOUT_SECS", 0.01)


def publisher(clients=None, host: str | None = "broker.local", **kwargs) -> MqttPublisher:
    clients = {} if clients is None else clients
    return MqttPublisher(clients, API_NAMES, device_id="sister-hat", broker_host=host, **kwargs)


# --- device id: pi-telemetry's device_id.rs, ported ----------------------------------


def test_explicit_device_id_wins_over_hostname():
    assert resolve_device_id("sister-hat", "raspberrypi") == "sister-hat"


def test_device_id_falls_back_to_hostname_when_unset_or_blank():
    assert resolve_device_id(None, "vorkin-rbpi-z2w") == "vorkin-rbpi-z2w"
    assert resolve_device_id("  ", "pi") == "pi"


def test_device_id_is_sanitised_for_use_as_a_topic_level():
    assert resolve_device_id("Living Room/HAT#1+", None) == "living-room-hat-1-"


def test_device_id_errors_when_nothing_usable():
    with pytest.raises(ValueError):
        resolve_device_id(None, None)
    with pytest.raises(ValueError):
        resolve_device_id("///", None)


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

    assert set(components) == {"glowmarkt", "tfl", "problem"}
    assert components["tfl"]["platform"] == "sensor"
    assert components["tfl"]["device_class"] == "enum"
    assert components["tfl"]["options"] == [s.value for s in ClientStatus]
    assert components["tfl"]["value_template"] == "{{ value_json.tfl }}"
    assert components["problem"]["platform"] == "binary_sensor"
    assert components["problem"]["device_class"] == "problem"


def test_every_component_reads_the_state_topic_and_expires():
    components = json.loads(build_discovery_payload("sister-hat", API_NAMES))["components"].values()

    assert {c["state_topic"] for c in components} == {"pi-telemetry/sister-hat/countdown/state"}
    assert {c["expire_after"] for c in components} == {180}


def test_unique_ids_are_distinct_per_host_and_metric():
    def unique_ids(device_id):
        components = json.loads(build_discovery_payload(device_id, API_NAMES))["components"]
        return [c["unique_id"] for c in components.values()]

    a, b = unique_ids("host-a"), unique_ids("host-b")

    assert len(set(a)) == len(a)
    assert not set(a) & set(b)


# --- state payload -------------------------------------------------------------------


def test_state_payload_reports_each_clients_status():
    pub = publisher({"glowmarkt": StubClient(ClientStatus.CONNECTED), "tfl": StubClient(ClientStatus.UNINITIALISED)})

    assert json.loads(pub.build_state_payload()) == {"glowmarkt": "connected", "tfl": "uninitialised", "problem": False}


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


# --- connecting and publishing -------------------------------------------------------


def test_initialise_connects_and_announces_the_device_retained():
    pub = publisher(username="ha", password="secret", port=1884)

    asyncio.run(pub.initialise())

    (fake,) = FakeMqttClient.instances
    assert pub.status == ClientStatus.CONNECTED
    assert fake.address == ("broker.local", 1884)
    assert fake.credentials == ("ha", "secret")
    assert fake.client_id == "countdown-sister-hat"  # pi-telemetry's is "pi-telemetry-<id>"
    assert [(m["topic"], m["qos"], m["retain"]) for m in fake.published] == [
        ("homeassistant/device/sister-hat_countdown/config", 1, True)
    ]


def test_update_publishes_the_health_state_not_retained_and_returns_no_panel():
    pub = publisher({"tfl": StubClient(ClientStatus.ERROR)})

    assert asyncio.run(pub.update()) is None  # update() initialises first

    state = FakeMqttClient.instances[0].published[-1]
    assert state["topic"] == "pi-telemetry/sister-hat/countdown/state"
    assert (state["qos"], state["retain"]) == (1, False)
    assert state["payload"] == {"glowmarkt": "disabled", "tfl": "error", "problem": True}


def test_a_refused_connection_marks_the_publisher_errored_and_raises():
    FakeMqttClient.connack_identifier = 135  # not authorised
    pub = publisher()

    with pytest.raises(ConnectionError):
        asyncio.run(pub.initialise())

    assert pub.status == ClientStatus.ERROR
    assert FakeMqttClient.instances[0].stopped


def test_an_unreachable_broker_marks_the_publisher_errored(monkeypatch):
    def unreachable(self, host, port):
        raise OSError("no route")

    monkeypatch.setattr(FakeMqttClient, "connect", unreachable)
    pub = publisher()

    with pytest.raises(OSError):
        asyncio.run(pub.initialise())

    assert pub.status == ClientStatus.ERROR


def test_a_dropped_connection_raises_and_reconnects_on_the_next_update():
    pub = publisher()
    asyncio.run(pub.update())
    FakeMqttClient.instances[0].drop_connection()
    pub.last_updated = None

    with pytest.raises(ConnectionError):
        asyncio.run(pub.update())
    assert pub.status == ClientStatus.ERROR

    pub.last_updated = None
    asyncio.run(pub.update())

    assert pub.status == ClientStatus.CONNECTED
    assert len(FakeMqttClient.instances) == 2
    assert FakeMqttClient.instances[0].stopped  # the old network loop is torn down, not leaked
    assert FakeMqttClient.instances[1].published[-1]["topic"] == "pi-telemetry/sister-hat/countdown/state"


def test_without_a_broker_host_it_is_disabled_and_never_connects():
    pub = publisher(host=None)

    assert asyncio.run(pub.update()) is None

    assert pub.is_disabled()
    assert FakeMqttClient.instances == []


def test_from_env_reads_the_same_variables_as_pi_telemetry(monkeypatch):
    monkeypatch.setenv("MQTT_BROKER_HOST", "192.168.0.181")
    monkeypatch.setenv("MQTT_BROKER_PORT", "1885")
    monkeypatch.setenv("MQTT_BROKER_USERNAME", "ha")
    monkeypatch.setenv("MQTT_BROKER_PASSWORD", "secret")
    monkeypatch.setenv("DEVICE_ID", "Sister HAT")

    pub = MqttPublisher.from_env({}, API_NAMES)

    assert (pub.broker_host, pub.port, pub.username, pub.password) == ("192.168.0.181", 1885, "ha", "secret")
    assert pub.device_id == "sister-hat"


def test_from_env_is_disabled_with_no_host_and_falls_back_to_the_default_port(monkeypatch):
    monkeypatch.setenv("MQTT_BROKER_PORT", "not-a-port")

    pub = MqttPublisher.from_env({}, API_NAMES)

    assert pub.is_disabled()
    assert pub.port == 1883


def test_from_env_never_needs_a_device_id_while_disabled(monkeypatch):
    monkeypatch.setattr(mqtt_publisher.socket, "gethostname", lambda: "")

    assert MqttPublisher.from_env({}, API_NAMES).is_disabled()

    monkeypatch.setenv("MQTT_BROKER_HOST", "broker.local")
    with pytest.raises(ValueError):
        MqttPublisher.from_env({}, API_NAMES)


def test_it_says_so_when_it_is_switched_off(capsys):
    MqttPublisher.from_env({}, API_NAMES)

    assert "MQTT_BROKER_HOST is not set" in capsys.readouterr().out


def test_it_logs_where_it_connected_and_when_the_connection_drops(capsys):
    pub = publisher(port=1884)

    asyncio.run(pub.initialise())
    assert "MQTT: connected to broker.local:1884 as countdown-sister-hat" in capsys.readouterr().out

    FakeMqttClient.instances[0].drop_connection()
    assert "MQTT: disconnected from broker.local:1884" in capsys.readouterr().out


def test_it_stays_quiet_about_being_off_when_a_host_is_set(monkeypatch, capsys):
    monkeypatch.setenv("MQTT_BROKER_HOST", "broker.local")

    MqttPublisher.from_env({}, API_NAMES)

    assert "not set" not in capsys.readouterr().out
