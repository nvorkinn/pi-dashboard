from importlib.metadata import entry_points

import requests
from pydantic import BaseModel

from countdown import app
from countdown.display_loop import safe_fetch


def test_safe_fetch_returns_func_result_on_success():
    assert safe_fetch(lambda: 42, fallback="fallback") == 42


def test_safe_fetch_returns_fallback_on_request_exception():
    def boom():
        raise requests.exceptions.ConnectionError("network down")

    assert safe_fetch(boom, fallback="fallback") == "fallback"


def test_safe_fetch_returns_fallback_on_validation_error():
    class Model(BaseModel):
        value: int

    def boom():
        Model.model_validate({"value": "not-an-int"})

    assert safe_fetch(boom, fallback="fallback") == "fallback"


def test_the_console_script_entry_point_actually_runs_the_app(monkeypatch):
    """The `countdown` script just calls what pyproject.toml points at. When that was an
    `async def`, the call created a coroutine, never awaited it, and the service
    crash-looped -- while every other test, which drive run() directly, stayed green."""
    ran = []

    async def fake_run():
        ran.append(True)

    monkeypatch.setattr(app, "run", fake_run)
    (entry_point,) = entry_points(group="console_scripts", name="countdown")

    assert entry_point.load()() is None
    assert ran == [True]
