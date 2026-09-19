"""How DisplayController copes with a Pi that has no e-paper panel connected: it used to
wait on the panel forever (see test_epd_busy_wait.py); now it asks once, runs without a
display if nothing answers, and asks again now and then in case one's been plugged in."""

from types import SimpleNamespace

import pytest
from PIL import Image

# countdown has to be imported before display.display: they import each other, and
# starting from display.display trips a circular import (test_display_snapshots.py gets
# the same effect from its own imports).
import countdown.api_registry  # noqa: F401
import display.display as display_module
from display.display import FULL_REFRESH_INTERVAL_S, DisplayController
from display.panel import Panel


class FakeEpd:
    def __init__(self, answers: bool):
        self.answers = answers
        self.fail_display = False
        self.calls: list[str] = []
        self.partials: list[tuple[tuple[int, int, int, int], int]] = []  # (region, buffer length)

    def _wake(self, name):
        self.calls.append(name)
        if not self.answers:
            raise RuntimeError("e-Paper still busy after 10s -- is the panel connected and powered?")

    def init(self):
        self._wake("init")

    def init_part(self):
        self._wake("init_part")

    def Clear(self):
        self.calls.append("Clear")

    def getbuffer(self, img):
        return b""

    def display(self, buf):
        self.calls.append("display")
        if self.fail_display:
            raise RuntimeError("e-Paper still busy after 60s")

    def display_Partial(self, buf, x0, y0, x1, y1):
        self.calls.append("display_Partial")
        self.partials.append(((x0, y0, x1, y1), len(buf)))

    def sleep(self):
        self.calls.append("sleep")


@pytest.fixture
def no_preview(monkeypatch):
    """img.show() would try to open a viewer; on a Pi with a driver it must never be called."""

    def fail(self, *args, **kwargs):
        raise AssertionError("img.show() called on a machine with an e-paper driver")

    monkeypatch.setattr(Image.Image, "show", fail)


def controller_with(epd: FakeEpd) -> DisplayController:
    controller = DisplayController()
    controller.display_enabled = True
    controller.epd = epd
    return controller


def test_a_panel_that_answers_is_painted(no_preview):
    epd = FakeEpd(answers=True)
    controller = controller_with(epd)

    controller.display_screen({})

    assert epd.calls == ["init", "display", "sleep"]
    assert controller.panel_connected is True


def test_no_panel_means_no_painting_and_no_preview_window(no_preview):
    epd = FakeEpd(answers=False)
    controller = controller_with(epd)

    img = controller.display_screen({})

    assert isinstance(img, Image.Image)  # still composed and returned
    assert epd.calls == ["init"]
    assert controller.panel_connected is False


def test_the_pairing_screen_is_skipped_too_without_a_panel(no_preview):
    from display.pairing_code_panel import PairingCodePanel

    epd = FakeEpd(answers=False)
    controller = controller_with(epd)

    controller.display_pairing_screen(PairingCodePanel("ABC123", "device-1", has_changed=True))

    assert epd.calls == ["init"]


def test_an_absent_panel_is_not_asked_again_until_the_retry_interval_passes(no_preview):
    epd = FakeEpd(answers=False)
    controller = controller_with(epd)

    controller.display_screen({})
    controller.display_screen({})
    assert epd.calls == ["init"]

    controller._next_probe = 0.0  # the retry interval has passed
    controller.display_screen({})
    assert epd.calls == ["init", "init"]


def test_a_panel_plugged_in_later_is_picked_up_and_painted(no_preview, capsys):
    epd = FakeEpd(answers=False)
    controller = controller_with(epd)
    controller.display_screen({})

    epd.answers = True
    controller._next_probe = 0.0
    controller.display_screen({})

    assert controller.panel_connected is True
    assert epd.calls[-2:] == ["display", "sleep"]
    assert "panel detected" in capsys.readouterr().out


def test_the_absence_is_logged_once_not_every_probe(no_preview, capsys):
    controller = controller_with(FakeEpd(answers=False))

    for _ in range(3):
        controller.display_screen({})
        controller._next_probe = 0.0

    assert capsys.readouterr().out.count("No e-paper panel responding") == 1


def test_shutdown_only_puts_a_known_awake_panel_to_sleep():
    absent, unprobed, present = FakeEpd(False), FakeEpd(True), FakeEpd(True)
    a, u, p = controller_with(absent), controller_with(unprobed), controller_with(present)
    a.panel_connected, u.panel_connected, p.panel_connected = False, None, True

    for controller in (a, u, p):
        controller.shutdown()

    assert (absent.calls, unprobed.calls, present.calls) == ([], [], ["sleep"])


def test_shutdown_survives_a_panel_that_stops_answering():
    epd = FakeEpd(True)
    epd.sleep = lambda: (_ for _ in ()).throw(RuntimeError("still busy"))
    controller = controller_with(epd)
    controller.panel_connected = True

    controller.shutdown()  # must not raise: it runs inside the SIGTERM handler


def test_the_pairing_code_goes_to_the_log_when_there_is_no_panel_to_show_it(no_preview, capsys):
    from display.pairing_code_panel import PairingCodePanel

    controller = controller_with(FakeEpd(answers=False))

    controller.display_pairing_screen(PairingCodePanel("ABC123", "device-1", has_changed=True))

    assert "ABC123" in capsys.readouterr().out


def test_the_pairing_code_is_not_logged_when_the_panel_shows_it(no_preview, capsys):
    from display.pairing_code_panel import PairingCodePanel

    controller = controller_with(FakeEpd(answers=True))

    controller.display_pairing_screen(PairingCodePanel("ABC123", "device-1", has_changed=True))

    assert "ABC123" not in capsys.readouterr().out


# --- what gets sent to the panel: skip / partial / full --------------------------------


class Solid(Panel):
    """A panel that renders as one flat colour at a fixed size."""

    def __init__(self, color: str, size: tuple[int, int]):
        self.color, self.size = color, size

    def render(self, image_width: int, image_height: int) -> Image.Image:
        return Image.new("RGBA", self.size, self.color)


def frame(arrivals: str = "black", weather: str = "gray", arrivals_width: int = 300) -> dict:
    return {"tfl": Solid(arrivals, (arrivals_width, 275)), "weather": Solid(weather, (200, 200))}


@pytest.fixture
def clock(monkeypatch):
    now = SimpleNamespace(value=1000.0)
    monkeypatch.setattr(display_module, "time", SimpleNamespace(monotonic=lambda: now.value))
    return now


def test_the_first_frame_is_one_full_refresh_with_no_clear_first(no_preview, clock):
    """Clear() is a whole black-and-white refresh of its own; display() overwrites every
    pixel anyway, so it only doubled the flashing."""
    epd = FakeEpd(answers=True)

    controller_with(epd).display_screen(frame())

    assert epd.calls == ["init", "display", "sleep"]


def test_an_unchanged_screen_is_left_alone_even_though_the_footer_time_moves_on(no_preview, clock):
    epd = FakeEpd(answers=True)
    controller = controller_with(epd)
    controller.display_screen(frame())
    calls = list(epd.calls)

    controller.display_screen(frame())  # the footer's timestamp has moved on; the picture hasn't

    assert epd.calls == calls


def test_only_the_arrivals_changing_is_a_partial_refresh_of_just_their_area(no_preview, clock):
    epd = FakeEpd(answers=True)
    controller = controller_with(epd)
    controller.display_screen(frame(arrivals="black"))
    epd.calls.clear()

    controller.display_screen(frame(arrivals="red"))

    assert epd.calls == ["init_part", "display_Partial", "sleep"]
    ((region, buffer_length),) = epd.partials
    assert region == (0, 5, 312, 280)  # arrivals sit at (5, 5), 300x275; x rounded out to whole bytes
    assert buffer_length == (312 // 8) * (280 - 5)


@pytest.mark.parametrize("width", [300, 301, 307, 250])
def test_the_partial_region_is_byte_aligned_and_covers_the_arrivals(no_preview, clock, width):
    epd = FakeEpd(answers=True)
    controller = controller_with(epd)
    controller.display_screen(frame("black", arrivals_width=width))

    controller.display_screen(frame("red", arrivals_width=width))

    (x0, _, x1, _), _ = epd.partials[-1]
    assert x0 % 8 == 0 and x1 % 8 == 0
    assert x0 <= 5 and x1 >= 5 + width


def test_a_change_outside_the_arrivals_is_a_full_refresh(no_preview, clock):
    epd = FakeEpd(answers=True)
    controller = controller_with(epd)
    controller.display_screen(frame(weather="gray"))
    epd.calls.clear()

    controller.display_screen(frame(weather="red"))

    assert epd.calls == ["init", "display", "sleep"]


def test_a_wider_arrivals_panel_moves_everything_beside_it_so_is_a_full_refresh(no_preview, clock):
    epd = FakeEpd(answers=True)
    controller = controller_with(epd)
    controller.display_screen(frame(arrivals_width=300))
    epd.calls.clear()

    controller.display_screen(frame(arrivals="red", arrivals_width=350))

    assert epd.calls == ["init", "display", "sleep"]


def test_partial_refreshes_give_way_to_a_full_one_after_the_interval_to_clear_ghosting(no_preview, clock):
    epd = FakeEpd(answers=True)
    controller = controller_with(epd)
    controller.display_screen(frame(arrivals="black"))

    clock.value += FULL_REFRESH_INTERVAL_S - 1
    epd.calls.clear()
    controller.display_screen(frame(arrivals="red"))
    assert epd.calls == ["init_part", "display_Partial", "sleep"]

    clock.value += 2  # now more than the interval since the full refresh
    epd.calls.clear()
    controller.display_screen(frame(arrivals="black"))
    assert epd.calls == ["init", "display", "sleep"]

    clock.value += 1  # ...and that reset the clock
    epd.calls.clear()
    controller.display_screen(frame(arrivals="red"))
    assert epd.calls == ["init_part", "display_Partial", "sleep"]


def test_a_failed_paint_forgets_what_is_on_the_panel_so_the_next_frame_is_repainted_in_full(no_preview, clock):
    epd = FakeEpd(answers=True)
    controller = controller_with(epd)
    epd.fail_display = True
    with pytest.raises(RuntimeError):
        controller.display_screen(frame())

    epd.fail_display = False
    epd.calls.clear()
    controller.display_screen(frame())  # same picture, but the panel's state is unknown

    assert epd.calls == ["init", "display", "sleep"]


def test_a_frame_that_never_reached_a_missing_panel_is_painted_once_one_appears(no_preview, clock):
    epd = FakeEpd(answers=False)
    controller = controller_with(epd)
    controller.display_screen(frame())

    epd.answers = True
    controller._next_probe = 0.0
    epd.calls.clear()
    controller.display_screen(frame())

    assert epd.calls == ["init", "display", "sleep"]


def test_the_pairing_screen_replaces_the_picture_so_the_next_frame_is_repainted_in_full(no_preview, clock):
    from display.pairing_code_panel import PairingCodePanel

    epd = FakeEpd(answers=True)
    controller = controller_with(epd)
    controller.display_screen(frame())
    controller.display_pairing_screen(PairingCodePanel("ABC123", "device-1", has_changed=True))
    assert "Clear" not in epd.calls
    epd.calls.clear()

    controller.display_screen(frame())  # identical to what was shown before the pairing screen

    assert epd.calls == ["init", "display", "sleep"]


def test_with_nothing_to_show_it_says_so_instead_of_a_blank_screen(no_preview, clock):
    epd = FakeEpd(answers=True)
    controller = controller_with(epd)

    img = controller.display_screen({})

    centre = img.convert("L").crop((100, 190, 700, 290))
    assert centre.getextrema()[0] < 100  # dark text pixels, not just white
    assert epd.calls == ["init", "display", "sleep"]

    epd.calls.clear()
    controller.display_screen({})  # and it doesn't keep repainting it
    assert epd.calls == []


def test_the_splash_is_one_full_paint_without_a_clear_and_resets_what_is_remembered(no_preview, clock):
    from display.splash_panel import SplashPanel

    epd = FakeEpd(answers=True)
    controller = controller_with(epd)
    controller.display_screen(frame())
    epd.calls.clear()

    controller.display_splash(SplashPanel())
    assert epd.calls == ["init", "display", "sleep"]

    epd.calls.clear()
    controller.display_screen(frame())  # same picture as before, but the panel now shows the splash
    assert epd.calls == ["init", "display", "sleep"]


def test_the_splash_on_a_pi_with_no_panel_is_skipped_quietly(no_preview, clock):
    from display.splash_panel import SplashPanel

    epd = FakeEpd(answers=False)

    img = controller_with(epd).display_splash(SplashPanel())

    assert isinstance(img, Image.Image)
    assert epd.calls == ["init"]
