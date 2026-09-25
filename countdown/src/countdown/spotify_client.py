import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from countdown.abstract_client import AbstractClient
from countdown.config_manager import SpotifyConfig
from countdown.http import DEFAULT_TIMEOUT
from countdown.models import Artist, Queue, TopResponse, Track
from display.panel import Panel
from display.spotify_panel import SpotifyPanel
from display.spotify_top_artists_panel import SpotifyTopArtistsPanel
from display.spotify_top_panel import SpotifyTopPanel
from display.spotify_top_tracks_panel import SpotifyTopTracksPanel

CREDENTIALS_FILE = Path(".auth_broker_device")


@dataclass(frozen=True)
class PageConfig:
    """One of the pages the Spotify area rotates through. A page with nothing to show
    (update_function returns None) gives way to the next one."""

    update_function: Callable[[SpotifyClient, PageConfig], Panel | None]


@dataclass(frozen=True)
class TopPageConfig(PageConfig):
    update_function: Callable[[SpotifyClient, TopPageConfig], Panel | None]
    params: dict[str, str]
    period: str


class SpotifyClient(AbstractClient):
    """Talks to auth-broker (https://github.com/nvorkinn/auth-broker), the cloud
    service that handles Spotify OAuth and hosts this device's config centrally --
    gifted frames have no stable public address of their own, so the broker is the
    one place that needs real TLS.

    Registers itself on first run, persisting credentials to CREDENTIALS_FILE
    (gitignored, same treatment as .spotify_token_cache/config.json) so later runs
    just load them -- no network call needed at all once registered. Registration
    has to succeed for construction to succeed: without a device_id, nothing else
    here works anyway, same as SpotifyOAuth's eager validation today.

    Deliberately doesn't request a pairing code itself -- that's part of
    get_config()'s response (see BrokerConfig.pairing_code), checked fresh every
    cycle by the caller, not a one-time thing this class owns.
    """

    panel_title = "Spotify"
    panel_logo = "spotify_logo.png"

    def __init__(self, config: SpotifyConfig):
        super().__init__(config)
        self.page = -1
        self.base_url = os.environ["BROKER_URL"]
        if CREDENTIALS_FILE.exists():
            data = json.loads(CREDENTIALS_FILE.read_text())
            self.device_id: str = data["device_id"]
            self.device_secret: str = data["device_secret"]

    def _initialise(self) -> None:
        pass

    def _request(self, method: str, path: str, **kwargs) -> bytes:
        headers = {"Authorization": f"Bearer {self.device_secret}"}
        response = self.session.request(
            method, f"{self.base_url}{path}", headers=headers, timeout=DEFAULT_TIMEOUT, **kwargs
        )
        response.raise_for_status()
        return response.content

    def _update(self) -> Panel:
        """The next page in PAGES, or the one after if that has nothing to show. The
        broker refreshes and calls Spotify server-side, this device never sees a token."""
        for _ in range(2):
            self.page = (self.page + 1) % len(PAGES)
            page_config = PAGES[self.page]
            panel = page_config.update_function(self, page_config)
            if panel:
                return panel
        return self.message_panel("Nothing playing on:")

    def update_player(self, _page_config: PageConfig) -> Panel | None:
        """What's playing and what's up next, or None if nothing is playing."""
        queue = Queue.model_validate_json(self._request("GET", f"/api/devices/{self.device_id}/queue"))
        if queue.currently_playing is None:
            return None
        return SpotifyPanel(queue)

    def update_top(self, page_config: TopPageConfig) -> Panel:
        params = {**page_config.params, "limit": 5}
        top_tracks_bytes = self._request("GET", f"/api/devices/{self.device_id}/top/tracks", params=params)
        top_tracks_panel = SpotifyTopTracksPanel(TopResponse[Track].model_validate_json(top_tracks_bytes))
        top_artists_bytes = self._request("GET", f"/api/devices/{self.device_id}/top/artists", params=params)
        top_artists_panel = SpotifyTopArtistsPanel(TopResponse[Artist].model_validate_json(top_artists_bytes))
        return SpotifyTopPanel(page_config.period, top_tracks_panel, top_artists_panel)


PAGES: tuple[PageConfig, ...] = (
    PageConfig(SpotifyClient.update_player),
    TopPageConfig(SpotifyClient.update_top, {"time_range": "long_term"}, "12 months"),
    PageConfig(SpotifyClient.update_player),
    TopPageConfig(SpotifyClient.update_top, {"time_range": "short_term"}, "4 weeks"),
)
