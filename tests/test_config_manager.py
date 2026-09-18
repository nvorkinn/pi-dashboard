from countdown.config_manager import LiveConfig

# The `isolated_cwd` fixture used below is defined once, autouse, in tests/conftest.py.


def test_live_config_starts_empty(isolated_cwd):
    """LiveConfig is deliberately not env/settings-sourced -- broker-owned fields
    (including Glowmarkt, now that it's broker-provided too) should never pick up
    a stale local value, only ever a fresh broker fetch."""
    live = LiveConfig()
    assert live.tfl.app_key == ""
    assert live.tfl.stop_ids == []
    assert live.weather.location == ""
    assert live.spotify.enabled is False
    assert live.glowmarkt.username == ""
    assert live.glowmarkt.password == ""
    assert live.interval == 15


def test_live_config_ignores_env_vars(isolated_cwd, monkeypatch):
    monkeypatch.setenv("TFL__APP_KEY", "should-be-ignored")
    monkeypatch.setenv("GLOWMARKT__USERNAME", "should-be-ignored")
    monkeypatch.setenv("INTERVAL", "99")
    live = LiveConfig()
    assert live.tfl.app_key == ""
    assert live.glowmarkt.username == ""
    assert live.interval == 15
