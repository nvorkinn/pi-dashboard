from countdown.config_manager import AppConfig

# The `isolated_cwd` fixture used below is defined once, autouse, in tests/conftest.py.


def test_config_starts_empty(isolated_cwd):
    """AppConfig is deliberately not env/settings-sourced -- broker-owned fields
    (including Glowmarkt, now that it's broker-provided too) should never pick up
    a stale local value, only ever a fresh broker fetch."""
    config = AppConfig()
    assert config.tfl.app_key == ""
    assert config.tfl.stop_ids == []
    assert config.weather.location == ""
    assert config.spotify.enabled is False
    assert config.glowmarkt.username is None
    assert config.glowmarkt.password is None
    assert config.interval == 15


def test_config_ignores_env_vars(isolated_cwd, monkeypatch):
    monkeypatch.setenv("TFL__APP_KEY", "should-be-ignored")
    monkeypatch.setenv("GLOWMARKT__USERNAME", "should-be-ignored")
    monkeypatch.setenv("INTERVAL", "99")
    config = AppConfig()
    assert config.tfl.app_key == ""
    assert config.glowmarkt.username is None
    assert config.interval == 15
