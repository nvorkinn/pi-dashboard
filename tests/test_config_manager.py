from countdown.config_manager import AppConfig

# The `isolated_cwd` fixture used below is defined once, autouse, in tests/conftest.py.


def test_defaults_with_no_env(isolated_cwd):
    config = AppConfig()
    assert config.tfl.app_key == ""
    assert config.tfl.stop_ids == []
    assert config.interval == 15
    assert config.spotify.enabled is False
    assert config.broker_url == "https://auth.nikolaivorkinn.com"


def test_env_vars_populate_secrets(isolated_cwd, monkeypatch):
    monkeypatch.setenv("TFL__APP_KEY", "secret-key")
    monkeypatch.setenv("GLOWMARKT__USERNAME", "me@example.com")
    config = AppConfig()
    assert config.tfl.app_key == "secret-key"
    assert config.glowmarkt.username == "me@example.com"


def test_broker_url_overridable_via_env(isolated_cwd, monkeypatch):
    monkeypatch.setenv("BROKER_URL", "http://127.0.0.1:5000")
    config = AppConfig()
    assert config.broker_url == "http://127.0.0.1:5000"
