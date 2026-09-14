"""End-to-end tests for the config website, driven through Flask's own test client
(no real server thread needed) against mocked TfL HTTP responses via `responses`."""
import responses

from countdown.config_manager import config_manager
from countdown.flask import app

METRO_STOP_JSON = {
    "naptanId": "940GZZLUKNG",
    "commonName": "Kennington Underground Station",
    "modes": ["tube"],
    "lines": [{"name": "Northern"}],
    "additionalProperties": [],
    "children": [],
    "stopType": "NaptanMetroStation",
}


@responses.activate
def test_search_returns_tube_match(isolated_cwd):
    responses.add(responses.GET, "https://api.tfl.gov.uk/StopPoint/Search/Kennington", json={
        "matches": [{"id": "940GZZLUKNG"}]
    })
    responses.add(responses.GET, "https://api.tfl.gov.uk/StopPoint/940GZZLUKNG", json=METRO_STOP_JSON)

    client = app.test_client()
    res = client.get("/api/search?q=Kennington")

    assert res.status_code == 200
    results = res.get_json()
    assert len(results) == 1
    assert results[0]["mode"] == "tube"
    assert results[0]["name"] == "Kennington"


def test_search_ignores_short_queries(isolated_cwd):
    client = app.test_client()
    res = client.get("/api/search?q=K")
    assert res.get_json() == []


def test_index_shows_empty_state_with_no_stops_configured(isolated_cwd):
    client = app.test_client()
    res = client.get("/")
    assert res.status_code == 200
    assert b"No stops configured" in res.data


@responses.activate
def test_index_resolves_configured_stops(isolated_cwd):
    config = config_manager.load_config()
    config.tfl.stop_ids = ["940GZZLUKNG"]
    config_manager.save_config(config)
    responses.add(responses.GET, "https://api.tfl.gov.uk/StopPoint/940GZZLUKNG", json=METRO_STOP_JSON)

    client = app.test_client()
    res = client.get("/")

    assert res.status_code == 200
    assert b"Kennington" in res.data


def test_post_saves_stops_interval_and_weather(isolated_cwd):
    client = app.test_client()
    res = client.post("/", data={
        "stops_order": "940GZZLUKNG,490000123W",
        "interval": "42",
        "weather_location": "Oslo,NO",
        "spotify_enabled": "on",
    })

    assert res.status_code == 302
    assert res.headers["Location"] == "/"

    saved = config_manager.load_config()
    assert saved.tfl.stop_ids == ["940GZZLUKNG", "490000123W"]
    assert saved.interval == 42
    assert saved.weather.location == "Oslo,NO"
    assert saved.spotify.enabled is True


def test_post_never_writes_secrets_to_config_json(isolated_cwd):
    config = config_manager.load_config()
    config.tfl.app_key = "secret-key"
    config_manager.save_config(config)

    client = app.test_client()
    client.post("/", data={"stops_order": "940GZZLUKNG", "interval": "15"})

    written = (isolated_cwd / "config.json").read_text()
    assert "secret-key" not in written
