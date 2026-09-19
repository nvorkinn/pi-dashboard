import asyncio
from datetime import datetime, timedelta

from countdown.abstract_client import AbstractClient
from countdown.config_manager import TflConfig


class FakeClient(AbstractClient):
    poll_interval = timedelta(minutes=5)

    async def initialise(self) -> None:
        pass

    async def _update(self):
        return "panel"


def test_is_due_before_the_first_update():
    assert FakeClient().is_due


def test_update_records_when_it_ran_and_returns_the_panel():
    client = FakeClient()

    assert asyncio.run(client.update()) == "panel"

    assert client.last_updated is not None
    assert not client.is_due


def test_is_due_again_once_the_poll_interval_has_passed():
    client = FakeClient()
    client.last_updated = datetime.now() - timedelta(minutes=5, seconds=1)
    assert client.is_due

    client.last_updated = datetime.now() - timedelta(minutes=4)
    assert not client.is_due


def test_cache_and_compare_is_false_the_first_time_even_for_none():
    client = FakeClient()

    assert client._cache_and_compare("endpoint", None) is False
    assert client._cache_and_compare("endpoint", None) is True
    assert client._cache_and_compare("endpoint", "changed") is False


def test_needs_refresh_is_true_for_any_config_change_by_default():
    client = FakeClient(TflConfig(stop_ids=["a"]))

    assert not client.needs_refresh(TflConfig(stop_ids=["a"]))
    assert client.needs_refresh(TflConfig(stop_ids=["a", "b"]))
    assert client.needs_refresh(TflConfig(stop_ids=["a"], app_key="new"))
