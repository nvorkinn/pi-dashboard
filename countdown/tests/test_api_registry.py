import asyncio
import json

import pytest
from config_factory import make_config

from countdown.abstract_client import AbstractClient, ClientStatus
from countdown.api_registry import ApiRegistry, ClientClasses, FailedClient
from countdown.glow_client import GlowClient
from countdown.spotify_client import SpotifyClient
from countdown.tfl_client import TflClient
from countdown.weather_client import WeatherClient


class FakeClient(AbstractClient):
    """Scriptable stand-in: each update() returns/raises the next item in `results`."""

    def __init__(self, *results):
        super().__init__()
        self.results = list(results)
        self.initialised = False
        self.updates = 0

    def _initialise(self) -> None:
        self.initialised = True

    def _update(self):
        self.updates += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def registry_with(**clients: AbstractClient) -> ApiRegistry:
    registry = ApiRegistry()
    registry.clients.update(clients)
    return registry


def test_api_names_match_the_config_field_names():
    """build_from_config looks each client's config up by name on AppConfig."""
    config = make_config()
    for member in ClientClasses:
        assert hasattr(config, member.api_name)


def test_on_config_update_registers_the_enabled_clients(monkeypatch):
    monkeypatch.setenv("BROKER_URL", "https://broker.example.com")
    config = make_config()
    config.spotify.enabled = True
    registry = ApiRegistry()

    asyncio.run(registry.on_config_update(config))

    assert {name: type(client) for name, client in registry.clients.items()} == {
        "glowmarkt": GlowClient,
        "tfl": TflClient,
        "weather": WeatherClient,
        "spotify": SpotifyClient,
    }


def test_on_config_update_skips_disabled_clients():
    config = make_config()  # spotify is off until the broker says otherwise
    config.weather.enabled = False
    registry = ApiRegistry()

    asyncio.run(registry.on_config_update(config))

    assert set(registry.clients) == {"glowmarkt", "tfl"}


def test_on_config_update_initialises_new_clients_even_if_one_fails(monkeypatch):
    initialised = []

    async def broken(self):
        raise ConnectionError("down")

    async def healthy(self):
        initialised.append(self)

    monkeypatch.setattr(TflClient, "initialise", broken)
    monkeypatch.setattr(WeatherClient, "initialise", healthy)
    registry = ApiRegistry()

    asyncio.run(registry.on_config_update(make_config()))

    assert initialised == [registry.clients["weather"]]


def test_on_config_update_survives_a_client_that_cannot_be_built(monkeypatch):
    """SpotifyClient needs BROKER_URL and saved credentials to even be constructed."""
    config = make_config()
    config.spotify.enabled = True  # BROKER_URL is unset in tests, so this raises KeyError
    registry = ApiRegistry()

    asyncio.run(registry.on_config_update(config))

    assert registry.clients["spotify"].status == ClientStatus.ERROR
    assert "tfl" in registry.clients


def test_unchanged_config_keeps_the_existing_clients_and_their_panels():
    registry = ApiRegistry()
    asyncio.run(registry.on_config_update(make_config()))
    before = dict(registry.clients)
    registry.panels["tfl"] = "arrivals"

    asyncio.run(registry.on_config_update(make_config()))

    assert all(registry.clients[name] is client for name, client in before.items())
    assert registry.panels == {"tfl": "arrivals"}


def test_a_changed_config_replaces_only_that_client_and_drops_its_stale_panel():
    registry = ApiRegistry()
    asyncio.run(registry.on_config_update(make_config()))
    old_tfl, old_weather = registry.clients["tfl"], registry.clients["weather"]
    registry.panels.update(tfl="old arrivals", weather="sunny")
    changed = make_config()
    changed.tfl.stop_ids = ["940GZZLUKNG"]  # resolving it fails offline, which is fine here

    asyncio.run(registry.on_config_update(changed))

    assert registry.clients["tfl"] is not old_tfl
    assert registry.clients["tfl"].config.stop_ids == ["940GZZLUKNG"]
    assert registry.clients["weather"] is old_weather
    assert registry.panels == {"weather": "sunny"}


def test_a_client_that_is_switched_off_is_dropped_with_its_panel():
    registry = ApiRegistry()
    asyncio.run(registry.on_config_update(make_config()))
    registry.panels["weather"] = "sunny"
    off = make_config()
    off.weather.enabled = False

    asyncio.run(registry.on_config_update(off))

    assert "weather" not in registry.clients
    assert "weather" not in registry.panels


def test_a_change_the_client_says_is_irrelevant_does_not_rebuild_it():
    """Open-Meteo is keyless, so WeatherClient ignores api_key changes -- rebuilding
    would only throw away its cached coordinates and forecast."""
    registry = ApiRegistry()
    asyncio.run(registry.on_config_update(make_config()))
    weather = registry.clients["weather"]
    changed = make_config()
    changed.weather.api_key = "new-key"

    asyncio.run(registry.on_config_update(changed))
    assert registry.clients["weather"] is weather

    changed.weather.location = "Paris"
    asyncio.run(registry.on_config_update(changed))
    assert registry.clients["weather"] is not weather


def test_update_all_returns_each_clients_panel():
    registry = registry_with(tfl=FakeClient("arrivals"), weather=FakeClient("sunny"))

    assert asyncio.run(registry.update_all()) == {"tfl": "arrivals", "weather": "sunny"}


def test_update_all_only_polls_clients_that_are_due_but_still_returns_their_last_panel():
    """Glowmarkt polls every 15 minutes; the cycles in between must still draw the
    energy panel, not blank it."""
    tfl, glow = FakeClient("arrivals-1", "arrivals-2"), FakeClient("energy")
    registry = registry_with(tfl=tfl, glowmarkt=glow)
    asyncio.run(registry.update_all())
    tfl.last_updated -= tfl.poll_interval  # tfl is due again; glow (just polled) is not

    panels = asyncio.run(registry.update_all())

    assert (tfl.updates, glow.updates) == (2, 1)
    assert panels == {"tfl": "arrivals-2", "glowmarkt": "energy"}


def test_update_all_keeps_the_last_good_panel_when_a_client_raises():
    weather = FakeClient("sunny", ConnectionError("down"))
    registry = registry_with(weather=weather)
    asyncio.run(registry.update_all())
    weather.last_updated = None

    panels = asyncio.run(registry.update_all())

    assert panels == {"weather": "sunny"}


def test_update_all_replaces_the_last_panel_when_a_client_has_nothing_to_show():
    """None is a real answer (nothing playing, no location set), unlike an error."""
    spotify = FakeClient("now playing", None)
    registry = registry_with(spotify=spotify)
    asyncio.run(registry.update_all())
    spotify.last_updated = None

    assert asyncio.run(registry.update_all()) == {"spotify": None}


def test_update_all_omits_a_client_that_has_never_succeeded():
    registry = registry_with(tfl=FakeClient(RuntimeError("boom")), weather=FakeClient("sunny"))

    assert asyncio.run(registry.update_all()) == {"weather": "sunny"}


def test_update_all_publishes_health_after_polling_the_clients():
    tfl = FakeClient("arrivals")
    registry = registry_with(tfl=tfl)
    registry.pub = health = FakeClient(None)

    asyncio.run(registry.update_all())

    assert (tfl.updates, health.updates) == (1, 1)


def test_update_all_still_returns_the_panels_when_publishing_health_fails():
    registry = registry_with(weather=FakeClient("sunny"))
    registry.pub = FakeClient(ConnectionError("mqtt down"))

    assert asyncio.run(registry.update_all()) == {"weather": "sunny"}


def test_the_publisher_reads_the_registrys_own_client_dict():
    registry = registry_with(tfl=FakeClient("arrivals"))

    assert registry.pub.clients is registry.clients
    assert registry.pub.api_names == [member.api_name for member in ClientClasses]


@pytest.mark.parametrize("bad", [ValueError("bad"), KeyError("bad")])
def test_update_all_never_lets_one_clients_failure_escape(bad):
    registry = registry_with(a=FakeClient(bad), b=FakeClient("fine"))

    assert asyncio.run(registry.update_all())["b"] == "fine"


def test_a_client_that_could_not_be_built_shows_as_an_error_in_the_health_payload():
    config = make_config()
    config.spotify.enabled = True  # BROKER_URL is unset in tests, so building it raises
    registry = ApiRegistry()

    asyncio.run(registry.on_config_update(config))

    payload = json.loads(registry.pub.build_state_payload())
    assert payload["spotify"] == "error"
    assert payload["problem"] is True


def test_a_client_that_could_not_be_built_is_reported_again_by_update_all_without_raising(capsys):
    config = make_config()
    config.spotify.enabled = True
    registry = ApiRegistry()
    asyncio.run(registry.on_config_update(config))
    capsys.readouterr()

    panels = asyncio.run(registry.update_all())

    assert "spotify" not in panels
    assert "Error updating spotify" in capsys.readouterr().out


def test_a_failed_client_is_rebuilt_when_its_config_changes_and_dropped_when_switched_off():
    failed = FailedClient(make_config().spotify, KeyError("BROKER_URL"))

    assert failed.needs_refresh(make_config(spotify={"enabled": True}).spotify)

    registry = registry_with(spotify=failed)
    registry.panels["spotify"] = "old panel"
    asyncio.run(registry.on_config_update(make_config()))  # spotify is disabled in the new config
    assert "spotify" not in registry.clients
