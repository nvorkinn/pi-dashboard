import json

from countdown.config_manager import AppConfig, ConfigManager

# The `isolated_cwd` fixture used below is defined once, autouse, in tests/conftest.py.


def test_defaults_with_no_env_or_json(isolated_cwd):
    config = AppConfig()
    assert config.tfl_api_app_key == ""
    assert config.stops == []
    assert config.interval == 15
    assert config.spotify.enabled is False


def test_env_vars_populate_secrets(isolated_cwd, monkeypatch):
    monkeypatch.setenv("TFL_API_APP_KEY", "secret-key")
    monkeypatch.setenv("SPOTIFY__CLIENT_ID", "client-123")
    config = AppConfig()
    assert config.tfl_api_app_key == "secret-key"
    assert config.spotify.client_id == "client-123"


def test_json_file_provides_non_secret_settings(isolated_cwd):
    (isolated_cwd / "config.json").write_text(json.dumps({
        "stops": ["940GZZLUKNG"],
        "interval": 42,
    }))
    config = AppConfig()
    assert config.stops == ["940GZZLUKNG"]
    assert config.interval == 42


def test_env_vars_take_priority_over_json_file(isolated_cwd, monkeypatch):
    (isolated_cwd / "config.json").write_text(json.dumps({"interval": 42}))
    monkeypatch.setenv("INTERVAL", "7")
    config = AppConfig()
    assert config.interval == 7


def test_save_config_never_persists_secrets(isolated_cwd):
    manager = ConfigManager()
    config = AppConfig(
        tfl_api_app_key="secret-tfl-key",
        stops=["940GZZLUKNG"],
    )
    config.spotify.client_id = "spotify-id"
    config.spotify.client_secret = "spotify-secret"
    config.weather.api_key = "weather-key"
    config.glowmarkt.username = "me@example.com"
    config.glowmarkt.password = "hunter2"

    manager.save_config(config)

    written = json.loads((isolated_cwd / "config.json").read_text())
    assert "tfl_api_app_key" not in written
    assert "glowmarkt" not in written
    assert "client_id" not in written["spotify"]
    assert "client_secret" not in written["spotify"]
    assert "api_key" not in written["weather"]
    # Non-secret fields still get written
    assert written["stops"] == ["940GZZLUKNG"]


def test_save_config_reload_still_has_secrets_from_env(isolated_cwd, monkeypatch):
    """Regression: secrets scrubbed from config.json must still come back from .env."""
    monkeypatch.setenv("TFL_API_APP_KEY", "secret-tfl-key")
    manager = ConfigManager()
    config = manager.load_config()
    manager.save_config(config)

    reloaded = manager.load_config()
    assert reloaded.tfl_api_app_key == "secret-tfl-key"


def test_has_changed_reflects_mtime(isolated_cwd):
    manager = ConfigManager()
    config_path = isolated_cwd / "config.json"
    config_path.write_text("{}")

    manager.load_config()
    assert manager.has_changed() is False

    config_path.write_text('{"interval": 99}')
    import os
    import time
    os.utime(config_path, (time.time() + 5, time.time() + 5))
    assert manager.has_changed() is True


def test_has_changed_false_when_file_missing(isolated_cwd):
    manager = ConfigManager()
    assert manager.has_changed() is False
