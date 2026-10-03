import pytest

from countdown_core.utils.device_id import resolve_device_id

# pi-telemetry's device_id.rs, ported -- must resolve identically, or the two
# processes end up as two separate HA devices for the same host.


def test_explicit_device_id_wins_over_hostname():
    assert resolve_device_id("sister-hat", "raspberrypi") == "sister-hat"


def test_device_id_falls_back_to_hostname_when_unset_or_blank():
    assert resolve_device_id(None, "vorkin-rbpi-z2w") == "vorkin-rbpi-z2w"
    assert resolve_device_id("  ", "pi") == "pi"


def test_device_id_is_sanitised_for_use_as_a_topic_level():
    assert resolve_device_id("Living Room/HAT#1+", None) == "living-room-hat-1-"


def test_device_id_errors_when_nothing_usable():
    with pytest.raises(ValueError):
        resolve_device_id(None, None)
    with pytest.raises(ValueError):
        resolve_device_id("///", None)
