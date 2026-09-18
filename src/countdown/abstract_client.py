from abc import ABC

from countdown.http import build_retrying_session


class AbstractClient(ABC):  # noqa: B024 -- no abstract methods on purpose; ABC just marks it as a base
    """Base for the API clients (TflClient, GlowClient, BrokerClient, ...): just a
    shared session and a small per-endpoint cache, available to a client that wants
    to compare a fresh response against the last one it saw (BrokerClient uses this
    for pairing-code change detection). Not force-piped into every client/call --
    see https://github.com/nvorkinn/countdown/issues/54 for the larger plan to use
    this more broadly for change-detection (skip a repaint / e-paper refresh when
    nothing changed)."""

    def __init__(self):
        self.session = build_retrying_session()
        self.cache: dict[str, object] = {}

    def _cache_and_compare(self, endpoint: str, data: object) -> bool:
        """Returns True if the last call to the same endpoint returned the same data.
        Always False the first time an endpoint is seen -- there's nothing to compare
        against yet, not "unchanged" -- even if that first value happens to be None
        (checked via membership, not `is None`, so a legitimately-None value doesn't
        get mistaken for "never cached" on every subsequent call)."""
        is_first_time = endpoint not in self.cache
        cached = self.cache.get(endpoint)
        self.cache[endpoint] = data
        if is_first_time:
            return False
        return cached == data
