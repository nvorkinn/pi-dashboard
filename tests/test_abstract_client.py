import asyncio
from datetime import datetime, timedelta

import pytest

from countdown.abstract_client import AbstractClient, ClientStatus
from countdown.config_manager import TflConfig


class FakeClient(AbstractClient):
    poll_interval = timedelta(minutes=5)

    def __init__(self, config=None, initialise_failures: int = 0):
        super().__init__(config)
        self.initialise_failures = initialise_failures
        self.initialise_calls = 0
        self.update_calls = 0

    async def _initialise(self) -> None:
        self.initialise_calls += 1
        if self.initialise_failures:
            self.initialise_failures -= 1
            raise ConnectionError("API down")

    async def _update(self):
        self.update_calls += 1
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


def test_initialise_marks_the_client_connected():
    client = FakeClient()
    assert client.status == ClientStatus.UNINITIALISED

    asyncio.run(client.initialise())

    assert client.status == ClientStatus.CONNECTED


def test_failed_initialise_marks_the_client_errored_and_raises():
    client = FakeClient(initialise_failures=1)

    with pytest.raises(ConnectionError):
        asyncio.run(client.initialise())

    assert client.status == ClientStatus.ERROR


def test_update_initialises_a_client_that_never_was_then_not_again():
    client = FakeClient()

    asyncio.run(client.update())
    asyncio.run(client.update())

    assert (client.initialise_calls, client.update_calls) == (1, 2)


def test_update_retries_initialisation_after_an_earlier_failure():
    client = FakeClient(initialise_failures=1)
    with pytest.raises(ConnectionError):
        asyncio.run(client.initialise())  # e.g. the API was down at boot

    assert asyncio.run(client.update()) == "panel"

    assert client.status == ClientStatus.CONNECTED
    assert client.initialise_calls == 2


def test_failed_reinitialisation_raises_skips_the_update_and_waits_a_full_poll_interval():
    client = FakeClient(initialise_failures=1)

    with pytest.raises(ConnectionError):
        asyncio.run(client.update())

    assert client.status == ClientStatus.ERROR
    assert client.update_calls == 0
    assert not client.is_due  # not retried every cycle -- some APIs rate-limit repeated failures


def test_a_failing_update_does_not_trigger_reinitialisation():
    """Only a client that never got connected re-initialises; a connected one that has
    a bad poll (a blip, a 500) just tries again next time."""
    client = FakeClient()
    asyncio.run(client.update())

    async def failing_update():
        raise ConnectionError("blip")

    client._update = failing_update
    with pytest.raises(ConnectionError):
        asyncio.run(client.update())

    assert client.status == ClientStatus.CONNECTED


def test_disabled_client_stays_disabled_and_makes_no_calls():
    client = FakeClient()
    client.status = ClientStatus.DISABLED

    asyncio.run(client.initialise())
    assert asyncio.run(client.update()) is None

    assert client.status == ClientStatus.DISABLED
    assert (client.initialise_calls, client.update_calls) == (0, 0)
