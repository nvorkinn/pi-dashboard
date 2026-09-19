"""How DisplayController copes with a Pi that has no e-paper panel connected: it used to
wait on the panel forever (see test_epd_busy_wait.py); now it asks once, runs without a
display if nothing answers, and asks again now and then in case one's been plugged in."""

import pytest
from PIL import Image

# countdown has to be imported before display.display: they import each other, and
# starting from display.display trips a circular import (test_display_snapshots.py gets
# the same effect from its own imports).
import countdown.api_registry  # noqa: F401
from display.display import DisplayController


class FakeEpd:
    def __init__(self, answers: bool):
        self.answers = answers
        self.calls: list[str] = []

    def init(self):
        self.calls.append("init")
        if not self.answers:
            raise RuntimeError("e-Paper still busy after 10s -- is the panel connected and powered?")

    def Clear(self):
        self.calls.append("Clear")

    def getbuffer(self, img):
        return b""

    def display(self, buf):
        self.calls.append("display")

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

    assert epd.calls == ["init", "Clear", "display", "sleep"]
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
    assert epd.calls[-3:] == ["Clear", "display", "sleep"]
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
