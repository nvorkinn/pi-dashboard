from typing import override

from countdown.core.models import Artist, TopResponse
from countdown.spotify.spotify_abstract_top_panel import AbstractSpotifyTopSubPanel


class SpotifyTopArtistsPanel(AbstractSpotifyTopSubPanel):
    def __init__(self, top_response: TopResponse[Artist]) -> None:
        super().__init__("Top artists:", top_response)

    @override
    def format_line(self, idx: int, row: Artist) -> str:
        return f"{idx + 1}) {row.name}"
