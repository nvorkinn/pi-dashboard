"""The display targets: which one DISPLAY_TARGET picks, the raw panel buffer, and what
RemotePiTarget runs. EpdTarget is covered through the controller in test_display_controller.py."""

import subprocess

import pytest
from PIL import Image

import display.targets as targets_module
from display.targets import EpdTarget, PreviewTarget, RemotePiTarget, panel_bytes, target_from_env


def test_white_pixels_are_sent_as_zero_bits_and_black_as_one():
    white = Image.new("1", (16, 1), 1)
    black = Image.new("1", (16, 1), 0)

    assert panel_bytes(white) == bytearray([0x00, 0x00])
    assert panel_bytes(black) == bytearray([0xFF, 0xFF])


def test_a_region_sends_only_its_own_bytes():
    img = Image.new("1", (800, 480), 1)
    img.paste(0, (8, 10, 16, 11))  # one black byte, inside the region

    buf = panel_bytes(img, (8, 10, 24, 12))

    assert buf == bytearray([0xFF, 0x00, 0x00, 0x00])  # 16px wide = 2 bytes a row, 2 rows


def test_the_preview_opens_the_whole_picture(monkeypatch):
    shown = []
    monkeypatch.setattr(Image.Image, "show", lambda self: shown.append(self.size))

    assert PreviewTarget().paint(Image.new("1", (800, 480)), (0, 0, 8, 8)) is True
    assert shown == [(800, 480)]


class RecordingRun:
    def __init__(self):
        self.commands: list[list[str]] = []

    def __call__(self, cmd, check):
        assert check is True
        self.commands.append(cmd)


@pytest.fixture
def remote(monkeypatch, tmp_path):
    run = RecordingRun()
    monkeypatch.setattr(subprocess, "run", run)
    target = RemotePiTarget("pi@countdown.local", "countdown-dev")
    target.dev_dir = tmp_path  # keep the frame out of the real dev/ directory
    return target, run


def test_a_remote_paint_copies_the_frame_then_runs_the_script_on_the_pi(remote, tmp_path):
    target, run = remote

    assert target.paint(Image.new("1", (16, 1), 0)) is True

    rsync, ssh = run.commands
    assert rsync[0] == "rsync"
    assert rsync[-3:] == [
        str(tmp_path / "out" / "frame.bin"),
        str(tmp_path / "pi_display.py"),
        "pi@countdown.local:countdown-dev/",
    ]
    assert ssh[: len(RemotePiTarget.SSH)] == RemotePiTarget.SSH
    assert ssh[-2] == "pi@countdown.local"
    assert ssh[-1].endswith("pi_display.py frame.bin'")
    assert (tmp_path / "out" / "frame.bin").read_bytes() == bytes([0xFF, 0xFF])


def test_a_remote_partial_paint_passes_the_region_along(remote, tmp_path):
    target, run = remote

    target.paint(Image.new("1", (800, 480), 1), (0, 8, 16, 10))

    assert run.commands[1][-1].endswith("pi_display.py frame.bin 0 8 16 10'")
    assert len((tmp_path / "out" / "frame.bin").read_bytes()) == 4  # just the region: 2 bytes x 2 rows


def test_a_failed_copy_is_raised_not_swallowed(remote, monkeypatch):
    target, _ = remote

    def fail(cmd, check):
        raise subprocess.CalledProcessError(255, cmd)

    monkeypatch.setattr(subprocess, "run", fail)

    with pytest.raises(subprocess.CalledProcessError):
        target.paint(Image.new("1", (16, 1)))


def test_the_remote_target_needs_a_host():
    with pytest.raises(ValueError, match="PI_HOST"):
        RemotePiTarget("")


class FakeEpd:
    pass


@pytest.fixture
def env(monkeypatch):
    for name in ("DISPLAY_TARGET", "PI_HOST", "PI_DIR"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def no_driver():
    raise ImportError("No module named 'spidev'")


def test_auto_uses_the_panel_when_the_driver_loads(env):
    epd = FakeEpd()
    env.setattr(targets_module, "_load_epd", lambda: epd)

    target = target_from_env()

    assert isinstance(target, EpdTarget)
    assert target.epd is epd


def test_auto_falls_back_to_the_preview_without_a_driver(env):
    env.setattr(targets_module, "_load_epd", no_driver)

    assert isinstance(target_from_env(), PreviewTarget)


def test_asking_for_the_panel_explicitly_fails_without_a_driver(env):
    env.setenv("DISPLAY_TARGET", "epd")
    env.setattr(targets_module, "_load_epd", no_driver)

    with pytest.raises(ImportError):
        target_from_env()


def test_preview_is_chosen_without_touching_the_driver(env):
    env.setenv("DISPLAY_TARGET", " Preview ")
    env.setattr(targets_module, "_load_epd", no_driver)

    assert isinstance(target_from_env(), PreviewTarget)


def test_remote_takes_its_host_and_directory_from_the_environment(env):
    env.setenv("DISPLAY_TARGET", "remote")
    env.setenv("PI_HOST", "pi@countdown.local")
    env.setenv("PI_DIR", "elsewhere")

    target = target_from_env()

    assert isinstance(target, RemotePiTarget)
    assert (target.host, target.pi_dir) == ("pi@countdown.local", "elsewhere")


def test_remote_without_a_host_is_refused(env):
    env.setenv("DISPLAY_TARGET", "remote")

    with pytest.raises(ValueError, match="PI_HOST"):
        target_from_env()


def test_an_unknown_target_is_refused(env):
    env.setenv("DISPLAY_TARGET", "hdmi")

    with pytest.raises(ValueError, match="hdmi"):
        target_from_env()
