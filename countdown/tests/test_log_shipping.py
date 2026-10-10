import stat

import pytest

from countdown_credentials.log_shipping import ENV_FILE_VAR, enable_log_shipping


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / "env"
    monkeypatch.setenv(ENV_FILE_VAR, str(path))
    monkeypatch.setenv("DEVICE_NAME", "Sister HAT")
    return path


def test_writes_the_secret_and_device_name_for_fluent_bit(env_file):
    enable_log_shipping("shh")

    assert env_file.read_text() == "FLUENT_BIT_TOKEN=shh\nDEVICE_NAME=sister-hat\n"


def test_the_file_is_readable_by_its_owner_only(env_file):
    enable_log_shipping("shh")

    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


def test_does_nothing_without_an_env_file_configured(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_FILE_VAR, raising=False)
    monkeypatch.chdir(tmp_path)

    enable_log_shipping("shh")

    assert list(tmp_path.iterdir()) == []


def test_a_new_secret_replaces_the_old_one(env_file):
    enable_log_shipping("old")
    enable_log_shipping("new")

    assert "FLUENT_BIT_TOKEN=new\n" in env_file.read_text()


def test_an_unchanged_file_is_left_alone(env_file):
    enable_log_shipping("shh")
    modified = env_file.stat().st_mtime_ns

    enable_log_shipping("shh")

    assert env_file.stat().st_mtime_ns == modified


def test_an_unwritable_file_is_logged_not_raised(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv(ENV_FILE_VAR, str(tmp_path / "missing-dir" / "env"))

    enable_log_shipping("shh")

    assert "won't be shipped" in caplog.text
