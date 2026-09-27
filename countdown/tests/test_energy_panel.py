import pytest

import countdown  # noqa: F401, I001 -- see test_display_snapshots.py for why this comes first
from countdown.glow.energy_panel import EnergyPanel


@pytest.mark.parametrize(
    ("peak", "step", "axis_max"),
    [
        (0.07, 0.02, 0.08),
        (0.4, 0.1, 0.4),
        (1.65, 0.5, 2.0),
        (9.9, 2.5, 10.0),
        (15, 5, 15),
        (178.6, 50, 200),
        (310, 100, 400),
        (0, 1.0, 1.0),
    ],
)
def test_y_scale_picks_a_round_step_and_the_first_tick_above_the_peak(peak, step, axis_max):
    assert EnergyPanel._y_scale(peak) == pytest.approx((step, axis_max))


def test_render_draws_y_axis_tick_labels_left_of_the_bars():
    readings = [{"start": f"2026-09-25T{hour:02d}:00:00", "kwh": 1.5} for hour in range(24)]

    img = EnergyPanel(readings, 0).render(260, 200)

    # The chart is pushed right to leave a column for the tick labels, and that
    # column has them in it.
    bar_row = img.crop((0, 150, 260, 151))
    assert bar_row.getbbox()[0] > 15
    assert img.crop((0, 40, 15, 150)).getbbox() is not None
