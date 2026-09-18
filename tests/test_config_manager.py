from countdown.config_manager import AppConfig, LiveConfig

# The `isolated_cwd` fixture used below is defined once, autouse, in tests/conftest.py.


def test_app_config_defaults_with_no_env(isolated_cwd):
    config = AppConfig()
    assert config.broker_url == "https://auth.nikolaivorkinn.com"
    assert config.glowmarkt.username == ""


def test_app_config_env_vars_populate_glowmarkt(isolated_cwd, monkeypatch):
    monkeypatch.setenv("GLOWMARKT__USERNAME", "me@example.com")
    monkeypatch.setenv("GLOWMARKT__PASSWORD", "hunter2")
    config = AppConfig()
    assert config.glowmarkt.username == "me@example.com"
    assert config.glowmarkt.password == "hunter2"


def test_broker_url_overridable_via_env(isolated_cwd, monkeypatch):
    monkeypatch.setenv("BROKER_URL", "http://127.0.0.1:5000")
    config = AppConfig()
    assert config.broker_url == "http://127.0.0.1:5000"


def test_live_config_starts_empty(isolated_cwd):
    """LiveConfig is deliberately not env/settings-sourced -- broker-owned fields
    should never pick up a stale local value, only ever a fresh broker fetch."""
    live = LiveConfig()
    assert live.tfl.app_key == ""
    assert live.tfl.stop_ids == []
    assert live.weather.location == ""
    assert live.spotify.enabled is False
    assert live.interval == 15


def test_live_config_ignores_env_vars(isolated_cwd, monkeypatch):
    monkeypatch.setenv("TFL__APP_KEY", "should-be-ignored")
    monkeypatch.setenv("INTERVAL", "99")
    live = LiveConfig()
    assert live.tfl.app_key == ""
    assert live.interval == 15
