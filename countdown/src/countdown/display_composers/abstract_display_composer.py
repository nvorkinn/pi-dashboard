from abc import ABC, abstractmethod

from PIL import Image

from countdown.core.api_registry import ClientClasses
from countdown.core.panel import Panel
from countdown.tfl.combined_arrival_panel import CombinedArrivalPanel
from countdown.utils.utils import GAP, TOTAL_WIDTH

# Where every layout puts the arrivals panel, the part of the screen that changes every
# minute and so the only part worth a partial refresh.
ARRIVALS_ORIGIN = (5, 5)
# The arrivals panel is as wide as its stops; a message in its place gets one stop's width.
ARRIVALS_MESSAGE_WIDTH = 262

Box = tuple[int, int, int, int]


class AbstractDisplayComposer(ABC):
    """One layout of the dashboard, chosen by choose_composer() when the config changes."""

    ARRIVALS_HEIGHT = 185

    # The TfL client fetches this many stops per update and pages through the rest.
    stops_shown: int = 2

    @abstractmethod
    def can_compose(self, available: frozenset[ClientClasses]) -> bool:
        """Whether this layout suits a device that can show `available`."""

    @abstractmethod
    def compose(self, panels: dict[str, Panel]) -> tuple[Image.Image, Box]:
        """The screen without its footer, and the box the arrivals panel occupies."""

    def _place(self, img: Image.Image, panel: Panel, x: int, y: int, width: int, height: int) -> Image.Image:
        """Renders `panel` and pastes it at (x, y). Returns what was rendered, since some
        panels (the arrivals) choose their own size."""
        rendered = panel.render(width, height)
        img.paste(rendered, (x, y), rendered)
        return rendered

    def _draw_top_row(self, img: Image.Image, panels: dict[str, Panel]) -> tuple[Box, int]:
        """The arrivals and weather, the same in every layout so the arrivals' partial
        refreshes keep working. Returns the arrivals' box and the y below the row."""
        arrival_panel = panels[ClientClasses.TFL.api_name]
        arrivals_width = TOTAL_WIDTH if isinstance(arrival_panel, CombinedArrivalPanel) else ARRIVALS_MESSAGE_WIDTH
        x, y = ARRIVALS_ORIGIN
        arrivals = self._place(img, arrival_panel, x, y, arrivals_width, self.ARRIVALS_HEIGHT)
        arrivals_box = (x, y, x + arrivals.size[0], y + arrivals.size[1])

        weather_x = arrivals_box[2] + GAP
        weather_panel = panels[ClientClasses.WEATHER.api_name]
        self._place(img, weather_panel, weather_x, y, TOTAL_WIDTH - weather_x - GAP, arrivals.size[1])
        return arrivals_box, arrivals_box[3] + GAP
