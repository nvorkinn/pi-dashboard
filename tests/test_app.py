from unittest.mock import MagicMock

import pydantic
import requests

from countdown.app import _reload_tfl_client_if_changed, safe_fetch


def test_safe_fetch_returns_func_result_on_success():
    assert safe_fetch(lambda: 42, fallback="fallback") == 42


def test_safe_fetch_returns_fallback_on_request_exception():
    def boom():
        raise requests.exceptions.ConnectionError("network down")

    assert safe_fetch(boom, fallback="fallback") == "fallback"


def test_safe_fetch_returns_fallback_on_validation_error():
    from pydantic import BaseModel

    class Model(BaseModel):
        value: int

    def boom():
        Model.model_validate({"value": "not-an-int"})

    assert safe_fetch(boom, fallback="fallback") == "fallback"


def test_reload_tfl_client_skips_when_config_unchanged(monkeypatch):
    old_tfl = MagicMock(name="old_tfl")
    config_manager = MagicMock()
    config_manager.has_changed.return_value = False

    result = _reload_tfl_client_if_changed(old_tfl, config_manager)

    assert result is old_tfl
    config_manager.load_config.assert_not_called()


def test_reload_tfl_client_builds_new_client_when_changed(monkeypatch):
    old_tfl = MagicMock(name="old_tfl")
    new_tfl = MagicMock(name="new_tfl")
    config_manager = MagicMock()
    config_manager.has_changed.return_value = True

    monkeypatch.setattr("countdown.app.TflClient", MagicMock(return_value=new_tfl))

    result = _reload_tfl_client_if_changed(old_tfl, config_manager)

    assert result is new_tfl


def test_reload_tfl_client_keeps_old_client_on_network_failure(monkeypatch):
    old_tfl = MagicMock(name="old_tfl")
    config_manager = MagicMock()
    config_manager.has_changed.return_value = True

    def boom(_config):
        raise requests.exceptions.ConnectionError("network is down")

    monkeypatch.setattr("countdown.app.TflClient", boom)

    result = _reload_tfl_client_if_changed(old_tfl, config_manager)

    assert result is old_tfl


def test_reload_tfl_client_keeps_old_client_on_validation_error(monkeypatch):
    old_tfl = MagicMock(name="old_tfl")
    config_manager = MagicMock()
    config_manager.has_changed.return_value = True

    from pydantic import BaseModel

    class Model(BaseModel):
        value: int

    def boom(_config):
        Model.model_validate({"value": "not-an-int"})

    monkeypatch.setattr("countdown.app.TflClient", boom)

    result = _reload_tfl_client_if_changed(old_tfl, config_manager)

    assert result is old_tfl
