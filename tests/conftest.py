import pytest

# Env vars AppConfig reads via pydantic-settings (see config_manager.py). Cleared so a
# developer's real .env values can never leak into a test run.
_APP_CONFIG_ENV_VARS = [
    "TFL_API_APP_KEY", "INTERVAL", "CONFIG_PORT",
    "WEATHER__API_KEY", "WEATHER__LOCATION",
    "SPOTIFY__CLIENT_ID", "SPOTIFY__CLIENT_SECRET", "SPOTIFY__REDIRECT_URI", "SPOTIFY__ENABLED",
    "GLOWMARKT__USERNAME", "GLOWMARKT__PASSWORD",
]


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    """Run every test in an empty temp directory with no app env vars set, so nothing
    can accidentally read (or write into) the real project's .env/config.json. Any test
    that wants config.json content should write it into this same tmp_path."""
    monkeypatch.chdir(tmp_path)
    for key in _APP_CONFIG_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
    return tmp_path
