from typing import override

from PIL import Image

from countdown.api_registry import ClientClasses
from countdown.display_composers.abstract_display_composer import GAP, AbstractDisplayComposer, Box
from display.panel import Panel
from display.utils import TOTAL_HEIGHT, TOTAL_WIDTH


class BaseComposer(AbstractDisplayComposer):
    """Neither Spotify nor Glowmarkt: four stops, a 2x2 grid beside the weather, and the
    notices full width below."""

    stops_shown = 4
    ARRIVALS_HEIGHT = 185 * 2

    @override
    def can_compose(self, available: frozenset[ClientClasses]) -> bool:
        return ClientClasses.SPOTIFY not in available and ClientClasses.GLOWMARKT not in available

    @override
    def compose(self, panels: dict[str, Panel]) -> tuple[Image.Image, Box]:
        img = Image.new("RGBA", (TOTAL_WIDTH, TOTAL_HEIGHT), (255, 255, 255, 255))
        arrivals_box, below_top_row = self._draw_top_row(img, panels)

        notices_panel = panels.get(ClientClasses.NOTICE_BOARD.api_name)
        if notices_panel is not None:
            width, height = TOTAL_WIDTH - 2 * GAP, TOTAL_HEIGHT - below_top_row - GAP
            self._place(img, notices_panel, GAP, below_top_row, width, height)

        return img, arrivals_box
