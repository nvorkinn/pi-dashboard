"""Runs on your machine: blanks the Pi's panel over ssh, the way DISPLAY_TARGET=remote paints
it (PI_HOST required, PI_DIR defaults to countdown-dev). Stop the service on the Pi first, or
it paints straight over the blank screen."""

from countdown.core.targets import RemotePiTarget

RemotePiTarget.from_env().clear()
