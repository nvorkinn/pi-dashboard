from datetime import datetime
from math import ceil

from PIL import Image, ImageDraw

from display.panel import Panel
from display.utils import GOOGLE_REGULAR, GOOGLE_SEMI

TITLE_FONT = GOOGLE_SEMI.font_variant(size=16)
LABEL_FONT = GOOGLE_REGULAR.font_variant(size=12)
NO_DATA_FONT = GOOGLE_REGULAR.font_variant(size=16)

PADDING = 4  # blank border round the whole panel
TITLE_GAP = 8  # between the title and the tallest bar
LABEL_GAP = 4  # between the baseline and the x-axis labels
MIN_LABEL_SPACING = 8  # horizontal gap kept between neighbouring x-axis labels
BASELINE_WIDTH = 2
BAR_FILL = 0.8  # fraction of each slot the bar covers; the rest is the gap between bars

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
        A bar chart of one page's readings, filling the given size.

        page_index: 0 = last 24h, 1 = last 31 days, 2 = this year
        readings: the usage_deltas() output for that page's time range - a list
                  of {"start": iso-string, "kwh": float} dicts

        Drawn straight onto pixels with bars on whole-pixel edges and text in 1-bit
        font mode, so there's nothing grey to threshold or dither for the e-paper.
        """
        img = Image.new("RGBA", (image_width, image_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        draw.fontmode = "1"
        page = PAGES[self.page_index]

        draw.text((PADDING, PADDING), page["title"], "black", font=TITLE_FONT)

        if not self.readings:
            draw.text((image_width / 2, image_height / 2), "No data", "black", font=NO_DATA_FONT, anchor="mm")
            return img

        labels = [page["label_fn"](row["start"]) for row in self.readings]
        values = [row["kwh"] for row in self.readings]

        label_height = LABEL_FONT.getbbox("0123456789:")[3]
        chart_left = PADDING
        chart_right = image_width - PADDING
        chart_top = PADDING + TITLE_FONT.getbbox(page["title"])[3] + TITLE_GAP
        baseline = image_height - PADDING - label_height - LABEL_GAP - BASELINE_WIDTH
        slot_width = (chart_right - chart_left) / len(values)

        self._draw_bars(draw, values, chart_left, chart_top, baseline, slot_width)
        draw.rectangle((chart_left, baseline, chart_right - 1, baseline + BASELINE_WIDTH - 1), fill="black")
        self._draw_labels(draw, labels, chart_left, baseline + BASELINE_WIDTH + LABEL_GAP, slot_width, image_width)
        return img

    @staticmethod
    def _draw_bars(draw, values, chart_left, chart_top, baseline, slot_width):
        # Scale to the tallest bar; negative/zero readings just draw nothing.
        peak = max(values) if max(values) > 0 else 1.0
        gap = max(1, round(slot_width * (1 - BAR_FILL) / 2))
        for i, value in enumerate(values):
            # Round each slot's edges, not the bar width, so bars stay evenly spread
            # rather than the rounding error piling up at the right-hand end.
            x0 = chart_left + round(i * slot_width) + gap
            x1 = chart_left + round((i + 1) * slot_width) - gap - 1
            top = baseline - round(max(value, 0) / peak * (baseline - chart_top))
            if top < baseline and x1 >= x0:
                draw.rectangle((x0, top, x1, baseline - 1), fill="black")

    @staticmethod
    def _draw_labels(draw, labels, chart_left, y, slot_width, image_width):
        # Label every nth bar, n being just enough that the widest label fits
        # between neighbours without overlapping.
        widest = max(LABEL_FONT.getlength(label) for label in labels)
        stride = max(1, ceil((widest + MIN_LABEL_SPACING) / slot_width))
        for i in range(0, len(labels), stride):
            centre = chart_left + (i + 0.5) * slot_width
            half = LABEL_FONT.getlength(labels[i]) / 2
            # Skip a label hanging off the panel edge rather than nudging it in,
            # which would crowd its neighbour and break the even spacing.
            if centre - half >= 0 and centre + half <= image_width:
                draw.text((centre, y), labels[i], "black", font=LABEL_FONT, anchor="ma")
