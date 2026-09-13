import calendar
from datetime import datetime

from PIL import Image, ImageDraw
from math import ceil

from display.panel import Panel
from display.utils import TOTAL_WIDTH

width = ceil(TOTAL_WIDTH / 3)
height = 200
margin_left = 40
margin_right = 30
margin_top = 40
margin_bottom = 20

class EnergyPanel(Panel):
    def __init__(self, readings_day: list[float] | None, readings_month: list[float] | None, readings_year: list[float] | None):
        super().__init__()
        self.readings_day = readings_day
        self.readings_month = readings_month
        self.readings_year = readings_year

    def render(self, image_width: int, image_height: int) -> Image.Image:
        img = Image.new("L", (image_width, image_height), "white")

        now = datetime.now()
        today_header = now.strftime("%-d %B %Y")
        month_name = now.strftime("%B")
        year = now.strftime("%Y")

        img.paste(self._create_day_panel(today_header, self.readings_day), (0, 0))
        img.paste(self._create_month_panel(month_name, self.readings_month), (width, 0))
        img.paste(self._create_year_panel(year, self.readings_year), (width * 2, 0))
        return img

    @staticmethod
    def _create_day_panel(header: str, data: list[float] | None) -> Image.Image:
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)

        draw.text((image.size[0] / 2, margin_top - 22), header, anchor="ma", fill="black")

        if data is None:
            draw.text((image.size[0] / 2, height / 2), "Connecting...", anchor="ma", fill="black")
            return image

        chart_width = width - margin_left - margin_right
        chart_height = height - margin_top - margin_bottom

        max_val = max(data) if data and max(data) > 0 else 1.0

        # Draw axes
        baseline_y = height - margin_bottom
        draw.line([(margin_left, baseline_y), (width - margin_right, baseline_y)], fill="black", width=2)  # X-axis
        draw.line([(margin_left, margin_top), (margin_left, baseline_y)], fill="black", width=2)  # Y-axis

        # Y-axis label
        draw.text((margin_left - 10, margin_top - 22), "kWh", fill="black")

        # Y-axis ticks, gridlines, and numerical labels (3 tiers: 0, midpoint, max)
        num_ticks = 3
        for i in range(num_ticks):
            val_fraction = i / (num_ticks - 1)
            tick_y = baseline_y - (chart_height * val_fraction)
            tick_val = max_val * val_fraction

            # Draw faint horizontal grid line across the plot area
            if i > 0:
                draw.line([(margin_left, tick_y), (width - margin_right, tick_y)], fill="black", width=1)

            # Draw numerical label
            label = f"{tick_val:.1f}"
            draw.text((margin_left - 30, tick_y - 6), label, fill="black")

        # Calculate widths for 24 hourly columns
        num_bars = len(data)
        slot_width = chart_width / num_bars
        bar_width = slot_width * 0.75  # leaves a small gap between columns

        label_modulo = 3 if len(data) <= 15 else 5

        for i, val in enumerate(data):
            bar_height = (val / max_val) * chart_height

            x0 = margin_left + (i * slot_width) + (slot_width - bar_width) / 2
            y0 = baseline_y - bar_height
            x1 = x0 + bar_width
            y1 = baseline_y

            # Draw the energy column
            draw.rectangle([x0, y0, x1, y1], fill="black")

            # Add hour labels every 3 hours
            if i % label_modulo == 0:
                time_label = f"{i:02d}:00"
                draw.text((x0, baseline_y + 8), time_label, fill="black")

        return image

    @staticmethod
    def _create_month_panel(month: str, data: list[float] | None):
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)

        chart_width = width - margin_left - margin_right
        chart_height = height - margin_top - margin_bottom

        draw.text((image.size[0] / 2, margin_top - 22), month, anchor="ma", fill="black")

        if data is None:
            draw.text((image.size[0] / 2, height / 2), "Connecting...", anchor="ma", fill="black")
            return image

        max_val = max(data) if data and max(data) > 0 else 1.0

        baseline_y = height - margin_bottom
        draw.line([(margin_left, baseline_y), (width - margin_right, baseline_y)], fill="black", width=2)  # X-axis
        draw.line([(margin_left, margin_top), (margin_left, baseline_y)], fill="black", width=2)  # Y-axis

        draw.text((margin_left - 10, margin_top - 22), "kWh", fill="black")

        # Y-axis ticks, gridlines, and numerical labels
        num_ticks = 3
        for i in range(num_ticks):
            val_fraction = i / (num_ticks - 1)
            tick_y = baseline_y - (chart_height * val_fraction)
            tick_val = max_val * val_fraction

            if i > 0:
                draw.line([(margin_left, tick_y), (width - margin_right, tick_y)], fill="black", width=1)

            label = f"{tick_val:.1f}"
            draw.text((margin_left - 30, tick_y - 6), label, fill="black")

        # Calculate widths for up to 31 daily columns
        num_bars = len(data)
        slot_width = chart_width / num_bars
        bar_width = slot_width * 0.75  # leaves a small gap between columns

        label_modulo = 1 if len(data) <= 15 else 5

        for i, val in enumerate(data):
            bar_height = (val / max_val) * chart_height

            x0 = margin_left + (i * slot_width) + (slot_width - bar_width) / 2
            y0 = baseline_y - bar_height
            x1 = x0 + bar_width
            y1 = baseline_y

            draw.rectangle([x0, y0, x1, y1], fill="black")

            # Add day-of-the-month labels on day 1 and every 5 days to prevent clutter
            day_num = i + 1
            if day_num == 1 or day_num % label_modulo == 0:
                draw.text(((x0 + x1) / 2, baseline_y + 8), str(day_num), anchor="ma", fill="black")

        return image

    @staticmethod
    def _create_year_panel(year: str, data: list[float] | None):
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)

        chart_width = width - margin_left - margin_right
        chart_height = height - margin_top - margin_bottom

        draw.text((image.size[0] / 2, margin_top - 22), year, anchor="ma", fill="black")

        if data is None:
            draw.text((image.size[0] / 2, height / 2), "Connecting...", anchor="ma", fill="black")
            return image

        max_val = max(data) if data and max(data) > 0 else 1.0

        baseline_y = height - margin_bottom
        draw.line([(margin_left, baseline_y), (width - margin_right, baseline_y)], fill="black", width=2)  # X-axis
        draw.line([(margin_left, margin_top), (margin_left, baseline_y)], fill="black", width=2)  # Y-axis

        draw.text((margin_left - 10, margin_top - 22), "kWh", fill="black")

        # Y-axis ticks, gridlines, and numerical labels
        num_ticks = 3
        for i in range(num_ticks):
            val_fraction = i / (num_ticks - 1)
            tick_y = baseline_y - (chart_height * val_fraction)
            tick_val = max_val * val_fraction

            if i > 0:
                draw.line([(margin_left, tick_y), (width - margin_right, tick_y)], fill="black", width=1)

            label = f"{tick_val:.1f}"
            draw.text((margin_left - 30, tick_y - 6), label, fill="black")

        # Calculate widths for up to 31 daily columns
        num_bars = len(data)
        slot_width = chart_width / num_bars
        bar_width = slot_width * 0.75  # leaves a small gap between columns

        for i, val in enumerate(data):
            bar_height = (val / max_val) * chart_height

            x0 = margin_left + (i * slot_width) + (slot_width - bar_width) / 2
            y0 = baseline_y - bar_height
            x1 = x0 + bar_width
            y1 = baseline_y

            draw.rectangle([x0, y0, x1, y1], fill="black")

            label = calendar.month_name[i + 1][0]
            draw.text(((x0 + x1) / 2, baseline_y + 8), label, anchor="ma", fill="black")

        return image
