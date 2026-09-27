from typing import override

from PIL import Image

from countdown.core.api_registry import ClientClasses
from countdown.core.panel import Panel
from countdown.display_composers.abstract_display_composer import GAP, AbstractDisplayComposer, Box
from countdown.utils.utils import TOTAL_HEIGHT, TOTAL_WIDTH


class GlowComposer(AbstractDisplayComposer):
    """No Spotify: two columns below the top row -- the notices under the arrivals, the
    energy chart under the weather."""

    @override
    def can_compose(self, available: frozenset[ClientClasses]) -> bool:
        return ClientClasses.SPOTIFY not in available and ClientClasses.GLOWMARKT in available

    @override
    def compose(self, panels: dict[str, Panel]) -> tuple[Image.Image, Box]:
        img = Image.new("RGBA", (TOTAL_WIDTH, TOTAL_HEIGHT), (255, 255, 255, 255))
        arrivals_box, below_top_row = self._draw_top_row(img, panels)

        notices_panel = panels.get(ClientClasses.NOTICE_BOARD.api_name)
        notices_width = arrivals_box[2] - arrivals_box[0]
        if notices_panel is not None:
            height = TOTAL_HEIGHT - below_top_row - GAP
            self._place(img, notices_panel, GAP, below_top_row, notices_width, height)

        energy_x = GAP + notices_width + GAP
        self._place(
            img,
            panels[ClientClasses.GLOWMARKT.api_name],
            energy_x,
            below_top_row,
            TOTAL_WIDTH - energy_x - GAP,
            TOTAL_HEIGHT - below_top_row - GAP,
        )
        return img, arrivals_box
