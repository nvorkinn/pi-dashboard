from datetime import datetime
from math import ceil

import matplotlib

matplotlib.use("Agg")  # headless - no X server / display needed on the Pi

import matplotlib.pyplot as plt
from PIL import Image

from display.panel import Panel
from display.utils import TOTAL_WIDTH

width = ceil(TOTAL_WIDTH / 3)
height = 200
margin_left = 40
margin_right = 30
margin_top = 40
margin_bottom = 20

DPI = 100  # figsize (inches) * DPI must equal the pixel dimensions above

BLACK = 0
WHITE = 255

# Pure black/white threshold applied to the final render. Anything darker
# than this (0-255) becomes black, everything else becomes white - no
# dithering, so bars and text stay crisp rather than speckled.
BW_THRESHOLD = 200

MARGIN = 16
LABEL_FONT_SIZE = 16
TITLE_FONT_SIZE = 22

BAR_COLOR = "black"
MAX_VISIBLE_LABELS = 10  # thin x-axis labels so they don't overlap

# CHART_WIDTH = DISPLAY_WIDTH - 2 * MARGIN
# CHART_HEIGHT = DISPLAY_HEIGHT - 2 * MARGIN

PAGES = [
    {
        "title": "Last 24 hours (kWh)",
        "label_fn": lambda iso: datetime.fromisoformat(iso).strftime("%H:%M"),
    },
    {
        "title": "Last 31 days (kWh)",
        "label_fn": lambda iso: datetime.fromisoformat(iso).strftime("%d %b"),
    },
    {
        "title": "This year (kWh)",
        "label_fn": lambda iso: datetime.fromisoformat(iso).strftime("%b"),
    },
]


class EnergyPanel(Panel):
    def __init__(self, readings: list[dict], page_index: int):
        super().__init__()
        self.page_index = page_index
        self.readings = readings

    def render(self, image_width: int, image_height: int) -> Image.Image:
        """
        Build a single full-screen page.

        page_index: 0 = last 24h, 1 = last 31 days, 2 = this year
        usage: the usage_deltas() output for that page's time range - a list
               of {"start": iso-string, "kwh": float} dicts

        Returns a Pillow Image (mode "1", pure black/white) ready for your
        Waveshare driver (epd.display(...) or epd.displayPartial(...),
        depending on refresh mode).
        """
        page = PAGES[self.page_index]
        values = self.readings
        labels = [page["label_fn"](row["start"]) for row in self.readings]

        fig = plt.figure(figsize=(image_width / DPI, image_height / DPI), dpi=DPI)
        ax = fig.add_subplot(111)

        if not values:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes, fontsize=14)
            ax.axis("off")
        else:
            x = range(len(values))
            extracted = [reading["kwh"] for reading in values]
            ax.bar(x, extracted, color=BAR_COLOR, width=0.8)

            # Thin the labels so they don't overlap, same idea as the
            # label_stride logic in the original Pillow version.
            stride = max(1, len(values) // MAX_VISIBLE_LABELS)
            ax.set_xticks(list(x)[::stride])
            ax.set_xticklabels(labels[::stride], rotation=0, fontsize=9)

            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_visible(False)
            ax.set_yticks([])
            ax.margins(x=0.01)

        ax.set_title(page["title"], fontsize=14, loc="left")
        fig.tight_layout(pad=1.2)

        image = self._figure_to_bw_image(fig)
        plt.close(fig)
        return image

    def _figure_to_bw_image(self, fig):
        """Render a matplotlib figure straight to a pure black/white Pillow Image."""
        canvas = fig.canvas
        canvas.draw()
        width, height = canvas.get_width_height()
        rgba = canvas.buffer_rgba()
        image = Image.frombuffer("RGBA", (width, height), rgba, "raw", "RGBA", 0, 1)
        image = image.convert("L")
        # Threshold to pure black/white, no dithering - crisp edges for e-paper.
        image = image.point(lambda p: 255 if p > BW_THRESHOLD else 0, mode="L")
        return image.convert("1")
