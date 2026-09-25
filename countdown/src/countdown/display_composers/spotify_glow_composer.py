from typing import override

from PIL import Image

from countdown.api_registry import ClientClasses
from countdown.display_composers.abstract_display_composer import GAP, AbstractDisplayComposer, Box
from display.panel import Panel
from display.utils import TOTAL_HEIGHT, TOTAL_WIDTH

SPOTIFY_WIDTH = 536
SPOTIFY_HEIGHT = 120


class SpotifyGlowComposer(AbstractDisplayComposer):
    """Everything: the notices above Spotify on the left, the energy chart on the right.
    Also what's drawn before the first config arrives."""

    @override
    def can_compose(self, available: frozenset[ClientClasses]) -> bool:
        return {ClientClasses.SPOTIFY, ClientClasses.GLOWMARKT} <= available

    @override
    def compose(self, panels: dict[str, Panel]) -> tuple[Image.Image, Box]:
        img = Image.new("RGBA", (TOTAL_WIDTH, TOTAL_HEIGHT), (255, 255, 255, 255))
        arrivals_box, below_top_row = self._draw_top_row(img, panels)

        spotify_y = TOTAL_HEIGHT - SPOTIFY_HEIGHT - GAP
        spotify = self._place(
            img, panels[ClientClasses.SPOTIFY.api_name], GAP, spotify_y, SPOTIFY_WIDTH, SPOTIFY_HEIGHT
        )

        # Notices, in the gap between the arrivals and Spotify
        notices_panel = panels.get(ClientClasses.NOTICE_BOARD.api_name)
        if notices_panel is not None:
            self._place(img, notices_panel, GAP, below_top_row, spotify.size[0], spotify_y - GAP - below_top_row)

        energy_x = GAP + spotify.size[0] + GAP
        self._place(
            img,
            panels[ClientClasses.GLOWMARKT.api_name],
            energy_x,
            below_top_row,
            TOTAL_WIDTH - energy_x - GAP,
            TOTAL_HEIGHT - below_top_row - GAP,
        )
        return img, arrivals_box
