from typing import override

from PIL import Image

from countdown.api_registry import ClientClasses
from countdown.display_composers.abstract_display_composer import GAP, AbstractDisplayComposer, Box
from countdown.display_composers.spotify_glow_composer import SPOTIFY_HEIGHT
from display.panel import Panel
from display.utils import TOTAL_HEIGHT, TOTAL_WIDTH


class SpotifyComposer(AbstractDisplayComposer):
    """No energy chart (Glowmarkt isn't set up): the notices and Spotify both take the
    full width below the arrivals and weather, so notices get longer lines."""

    @override
    def can_compose(self, available: frozenset[ClientClasses]) -> bool:
        return ClientClasses.GLOWMARKT not in available

    @override
    def compose(self, panels: dict[str, Panel]) -> tuple[Image.Image, Box]:
        img = Image.new("RGBA", (TOTAL_WIDTH, TOTAL_HEIGHT), (255, 255, 255, 255))
        arrivals_box, below_top_row = self._draw_top_row(img, panels)
        width = TOTAL_WIDTH - 2 * GAP

        spotify_y = TOTAL_HEIGHT - SPOTIFY_HEIGHT - GAP
        self._place(img, panels[ClientClasses.SPOTIFY.api_name], GAP, spotify_y, width, SPOTIFY_HEIGHT)

        notices_panel = panels.get(ClientClasses.NOTICE_BOARD.api_name)
        if notices_panel is not None:
            self._place(img, notices_panel, GAP, below_top_row, width, spotify_y - GAP - below_top_row)
        return img, arrivals_box
