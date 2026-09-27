from typing import override

from countdown.core.models import TopResponse, Track
from countdown.spotify.spotify_abstract_top_panel import AbstractSpotifyTopSubPanel


class SpotifyTopTracksPanel(AbstractSpotifyTopSubPanel):
    def __init__(self, top_response: TopResponse[Track]) -> None:
        super().__init__("Top tracks:", top_response)

    @override
    def format_line(self, idx: int, row: Track) -> str:
        return f"{idx + 1}) {row.name} by {row.artists[0].name}"
