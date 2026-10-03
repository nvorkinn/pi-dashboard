"""The vendored driver's ReadBusy() must not wait forever: with no display connected that
would freeze the whole app. The driver is loaded here against a fake epdconfig (the real
one needs the Pi's GPIO)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

DRIVER = Path(__file__).parent.parent / "standalone" / "src" / "countdown_standalone" / "lib" / "epd7in5_V2.py"


class FakeEpdConfig(ModuleType):
    RST_PIN, DC_PIN, BUSY_PIN, CS_PIN = 17, 25, 24, 8

    def __init__(self, busy_reads: list[int]):
        super().__init__("epdconfig")
        self.busy_reads = busy_reads  # what the BUSY pin reads, in order; the last repeats
        self.delays: list[int] = []
        self.exited = 0

    def digital_read(self, pin):
        return self.busy_reads.pop(0) if len(self.busy_reads) > 1 else self.busy_reads[0]

    def delay_ms(self, ms):
        self.delays.append(ms)

    def digital_write(self, pin, value):
        pass

    def spi_writebyte(self, data):
        pass

    def module_exit(self):
        self.exited += 1


def load_driver(monkeypatch, busy_reads: list[int]):
    config = FakeEpdConfig(busy_reads)
    monkeypatch.setitem(sys.modules, "epdconfig", config)
    spec = importlib.util.spec_from_file_location("epd7in5_V2_under_test", DRIVER)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    return driver, config


def test_read_busy_returns_once_the_panel_releases_busy(monkeypatch):
    driver, config = load_driver(monkeypatch, busy_reads=[0, 0, 0, 1])

    driver.EPD().ReadBusy()

    assert config.exited == 0


def test_read_busy_sleeps_between_polls_instead_of_spinning(monkeypatch):
    driver, config = load_driver(monkeypatch, busy_reads=[0, 0, 0, 1])

    driver.EPD().ReadBusy()

    assert config.delays.count(20) >= 3  # once per still-busy poll, plus the final settle


def test_read_busy_gives_up_on_a_panel_that_never_responds_and_powers_down(monkeypatch):
    driver, config = load_driver(monkeypatch, busy_reads=[0])
    monkeypatch.setattr(driver, "BUSY_TIMEOUT_S", 0.05)

    with pytest.raises(RuntimeError, match="panel connected"):
        driver.EPD().ReadBusy()

    assert config.exited == 1


def test_init_gives_up_quickly_when_no_panel_answers_power_on(monkeypatch):
    """init()'s POWER ON wait has its own short timeout -- it's how a missing panel is told
    apart from a slow refresh, which gets the long one."""
    driver, config = load_driver(monkeypatch, busy_reads=[0])
    config.module_init = lambda: 0
    monkeypatch.setattr(driver, "POWER_ON_TIMEOUT_S", 0.05)

    with pytest.raises(RuntimeError, match="panel connected"):
        driver.EPD().init()

    assert config.exited == 1


def test_init_completes_when_the_panel_answers(monkeypatch):
    driver, config = load_driver(monkeypatch, busy_reads=[1])
    config.module_init = lambda: 0

    driver.EPD().init()

    assert config.exited == 0
