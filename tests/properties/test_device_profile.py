"""DeviceProfile invariants (memo W1 days 1-2).

Rules: a profile needs a non-empty device_id and a non-empty, duplicate-free,
ordered list of input modes. Order is the preference order.
"""
import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from farm.contracts.models import DeviceProfile, InputMode

modes = st.lists(st.sampled_from(InputMode), min_size=1, max_size=2, unique=True)


def test_rejects_empty_input_mode_list():
    with pytest.raises(ValidationError):
        DeviceProfile(device_id="seat-01", input_modes=[])


@pytest.mark.parametrize("mode", list(InputMode))
def test_rejects_duplicate_modes(mode):
    with pytest.raises(ValidationError):
        DeviceProfile(device_id="seat-01", input_modes=[mode, mode])


@pytest.mark.parametrize(
    "given_modes",
    [
        [InputMode.HID],
        [InputMode.ADB],
        [InputMode.HID, InputMode.ADB],
        [InputMode.ADB, InputMode.HID],
    ],
)
def test_accepts_valid_lists_and_keeps_order(given_modes):
    profile = DeviceProfile(device_id="seat-01", input_modes=given_modes)
    assert profile.input_modes == given_modes


@given(modes)
def test_any_unique_nonempty_list_is_accepted_in_order(given_modes):
    profile = DeviceProfile(device_id="seat-01", input_modes=given_modes)
    assert profile.input_modes == given_modes


@given(st.text(alphabet=" \t\n", max_size=5))
def test_rejects_blank_device_id(blank):
    with pytest.raises(ValidationError):
        DeviceProfile(device_id=blank, input_modes=[InputMode.HID])


def test_rejects_unknown_mode():
    with pytest.raises(ValidationError):
        DeviceProfile(device_id="seat-01", input_modes=["usb"])


def test_rejects_extra_fields():
    with pytest.raises(ValidationError):
        DeviceProfile(device_id="seat-01", input_modes=["hid"], colour="red")


def test_accepts_mode_names_as_strings():
    profile = DeviceProfile(device_id="seat-01", input_modes=["hid", "adb"])
    assert profile.input_modes == [InputMode.HID, InputMode.ADB]


def test_profile_is_immutable():
    profile = DeviceProfile(device_id="seat-01", input_modes=[InputMode.HID])
    with pytest.raises(ValidationError):
        profile.device_id = "seat-02"
