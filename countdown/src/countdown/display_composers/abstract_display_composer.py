from abc import ABC, abstractmethod

from PIL import Image

from countdown.api_registry import ClientClasses
from display.combined_arrival_panel import CombinedArrivalPanel
from display.panel import Panel
from display.utils import TOTAL_WIDTH, add_border

# Where every layout puts the arrivals panel, the part of the screen that changes every
# minute and so the only part worth a partial refresh.
ARRIVALS_ORIGIN = (5, 5)
ARRIVALS_HEIGHT = 185
# The arrivals panel is as wide as its stops; a message in its place gets one stop's width.
ARRIVALS_MESSAGE_WIDTH = 262
GAP = 5  # between panels, and between them and the screen's edge

Box = tuple[int, int, int, int]


class AbstractDisplayComposer(ABC):
    """One layout of the dashboard. DisplayController picks a composer whenever the config
    changes (see choose_composer), from the APIs that can actually be shown, then hands it
    every cycle's panels to arrange."""

    @abstractmethod
    def can_compose(self, available: frozenset[ClientClasses]) -> bool:
        """Whether this layout suits a device that can show `available` (see
        ApiRegistry.available)."""

    @abstractmethod
    def compose(self, panels: dict[str, Panel]) -> tuple[Image.Image, Box]:
        """The screen without its footer, and the box the arrivals panel occupies."""

    @staticmethod
    def _place(img: Image.Image, panel: Panel, x: int, y: int, width: int, height: int) -> Image.Image:
        """Renders `panel` at that size, borders it and pastes it at (x, y). Returns what
        was rendered, since some panels (the arrivals) choose their own size."""
        rendered = panel.render(width, height)
        add_border(rendered)
        img.paste(rendered, (x, y), rendered)
        return rendered

    def _draw_top_row(self, img: Image.Image, panels: dict[str, Panel]) -> tuple[Box, int]:
        """The arrivals at top-left and the weather beside them -- the same in every
        layout, so the arrivals' partial refreshes keep working. Returns the arrivals'
        box and the y just below the row, where the rest of the layout starts."""
        arrival_panel = panels[ClientClasses.TFL.api_name]
        arrivals_width = TOTAL_WIDTH if isinstance(arrival_panel, CombinedArrivalPanel) else ARRIVALS_MESSAGE_WIDTH
        x, y = ARRIVALS_ORIGIN
        arrivals = self._place(img, arrival_panel, x, y, arrivals_width, ARRIVALS_HEIGHT)
        arrivals_box = (x, y, x + arrivals.size[0], y + arrivals.size[1])

        weather_x = arrivals_box[2] + GAP
        weather_panel = panels[ClientClasses.WEATHER.api_name]
        self._place(img, weather_panel, weather_x, y, TOTAL_WIDTH - weather_x - GAP, arrivals.size[1])
        return arrivals_box, arrivals_box[3] + GAP
