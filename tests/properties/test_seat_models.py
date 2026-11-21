"""Seat models: roles, device matching, the enrollment table, seat state."""
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from farm.contracts.events import DeviceEvent, DeviceEventKind
from farm.contracts.models import DeviceProfile, InputMode
from farm.contracts.seats import (
    DeviceMatch,
    DeviceRole,
    SeatChange,
    SeatSpec,
    SeatState,
    SeatStatus,
    SeatTable,
)

HID = DeviceRole.HID_BOARD
CARD = DeviceRole.CAPTURE_CARD
PHONE = DeviceRole.PHONE


def make_event(by_id="usb-a", by_path=None):
    return DeviceEvent(
        kind=DeviceEventKind.ATTACHED,
        by_id=by_id,
        by_path=by_path,
        vendor_id="303a",
        product_id="1001",
        observed_ns=1,
    )


def profile(seat_id="seat-01", modes=(InputMode.HID,)):
    return DeviceProfile(device_id=seat_id, input_modes=list(modes))


def hid_seat(seat_id, controller_id, card_path):
    return SeatSpec(
        profile=profile(seat_id),
        devices={
            HID: DeviceMatch(by_id=controller_id),
            CARD: DeviceMatch(by_path=card_path),
        },
    )


# ---- DeviceMatch -----------------------------------------------------------

@pytest.mark.parametrize(
    "args",
    [dict(by_id="a"), dict(by_path="p"), dict(by_id="a", by_path="p")],
)
def test_match_accepts_identifier_combinations(args):
    DeviceMatch(**args)


def test_match_requires_at_least_one_identifier():
    with pytest.raises(ValidationError):
        DeviceMatch()


@pytest.mark.parametrize("args", [dict(by_id=""), dict(by_path="   ")])
def test_match_rejects_blank_identifiers(args):
    with pytest.raises(ValidationError):
        DeviceMatch(**args)


def test_match_by_id_only_ignores_the_path():
    match = DeviceMatch(by_id="usb-a")
    assert match.matches(make_event("usb-a", "p1"))
    assert match.matches(make_event("usb-a", None))
    assert not match.matches(make_event("usb-b"))


def test_match_by_path_only_needs_the_path():
    match = DeviceMatch(by_path="p1")
    assert match.matches(make_event("anything", "p1"))
    assert not match.matches(make_event("anything", "p2"))
    assert not match.matches(make_event("anything", None))


@pytest.mark.parametrize(
    "event_id, event_path, expected",
    [("usb-a", "p1", True), ("usb-a", "p2", False), ("usb-b", "p1", False)],
)
def test_match_with_both_identifiers_needs_both(event_id, event_path, expected):
    match = DeviceMatch(by_id="usb-a", by_path="p1")
    assert match.matches(make_event(event_id, event_path)) is expected


ident = st.text(alphabet=st.characters(whitelist_categories=("L", "N")), min_size=1, max_size=20)


@given(ident, ident)
def test_match_accepts_an_event_built_from_its_own_identifiers(by_id, by_path):
    match = DeviceMatch(by_id=by_id, by_path=by_path)
    assert match.matches(make_event(by_id, by_path))


def test_match_rejects_extra_fields():
    with pytest.raises(ValidationError):
        DeviceMatch(by_id="a", serial="1")


def test_match_is_immutable():
    match = DeviceMatch(by_id="a")
    with pytest.raises(ValidationError):
        match.by_id = "b"


# ---- SeatSpec --------------------------------------------------------------

def test_spec_accepts_a_standard_seat():
    spec = SeatSpec(
        profile=profile(),
        devices={HID: DeviceMatch(by_id="usb-ctrl"), CARD: DeviceMatch(by_path="p1")},
    )
    assert set(spec.devices) == {HID, CARD}


def test_spec_accepts_an_adb_only_seat():
    spec = SeatSpec(
        profile=profile(modes=(InputMode.ADB,)),
        devices={PHONE: DeviceMatch(by_id="phone-serial")},
    )
    assert set(spec.devices) == {PHONE}


def test_spec_accepts_a_seat_with_both_input_modes():
    spec = SeatSpec(
        profile=profile(modes=(InputMode.HID, InputMode.ADB)),
        devices={
            HID: DeviceMatch(by_id="usb-ctrl"),
            PHONE: DeviceMatch(by_id="phone-serial"),
            CARD: DeviceMatch(by_path="p1"),
        },
    )
    assert spec.profile.input_modes == [InputMode.HID, InputMode.ADB]


def test_spec_seat_id_is_the_profile_device_id():
    spec = SeatSpec(
        profile=profile("seat-07"),
        devices={HID: DeviceMatch(by_id="usb-ctrl"), CARD: DeviceMatch(by_path="p1")},
    )
    assert spec.seat_id == "seat-07"


def test_spec_accepts_dual_mode_seat_without_a_capture_card():
    # A phone with no video out is still a valid ADB seat even if a board is
    # listed. One fully supported mode is enough for enrollment.
    spec = SeatSpec(
        profile=profile(modes=(InputMode.HID, InputMode.ADB)),
        devices={HID: DeviceMatch(by_id="usb-ctrl"), PHONE: DeviceMatch(by_id="phone-serial")},
    )
    assert set(spec.devices) == {HID, PHONE}


def test_spec_rejects_board_only_hid_seat():
    with pytest.raises(ValidationError):
        SeatSpec(profile=profile(), devices={HID: DeviceMatch(by_id="usb-ctrl")})


def test_spec_rejects_hid_mode_without_a_hid_board():
    with pytest.raises(ValidationError):
        SeatSpec(profile=profile(), devices={CARD: DeviceMatch(by_path="p1")})


def test_spec_rejects_adb_mode_without_a_phone():
    with pytest.raises(ValidationError):
        SeatSpec(
            profile=profile(modes=(InputMode.ADB,)),
            devices={CARD: DeviceMatch(by_path="p1")},
        )


def test_spec_rejects_empty_devices():
    with pytest.raises(ValidationError):
        SeatSpec(profile=profile(), devices={})


def test_spec_rejects_unknown_role():
    with pytest.raises(ValidationError):
        SeatSpec(profile=profile(), devices={"usb_hub": DeviceMatch(by_id="x")})


def test_spec_accepts_role_names_as_strings():
    spec = SeatSpec(
        profile=profile(),
        devices={
            "hid_board": DeviceMatch(by_id="x"),
            "capture_card": DeviceMatch(by_path="p1"),
        },
    )
    assert HID in spec.devices


def test_spec_rejects_extra_fields():
    with pytest.raises(ValidationError):
        SeatSpec(
            profile=profile(),
            devices={HID: DeviceMatch(by_id="x")},
            colour="red",
        )


def test_spec_is_immutable():
    spec = SeatSpec(
        profile=profile(),
        devices={HID: DeviceMatch(by_id="x"), CARD: DeviceMatch(by_path="p1")},
    )
    with pytest.raises(ValidationError):
        spec.devices = {}


# ---- SeatTable -------------------------------------------------------------

def test_table_accepts_distinct_seats():
    table = SeatTable(
        seats=[hid_seat("seat-01", "usb-a", "p1"), hid_seat("seat-02", "usb-b", "p2")]
    )
    assert [s.seat_id for s in table.seats] == ["seat-01", "seat-02"]


def test_table_rejects_an_empty_seat_list():
    with pytest.raises(ValidationError):
        SeatTable(seats=[])


def test_table_rejects_duplicate_seat_ids():
    with pytest.raises(ValidationError):
        SeatTable(
            seats=[hid_seat("seat-01", "usb-a", "p1"), hid_seat("seat-01", "usb-b", "p2")]
        )


def test_table_rejects_a_by_id_claimed_by_two_seats():
    with pytest.raises(ValidationError):
        SeatTable(
            seats=[hid_seat("seat-01", "usb-x", "p1"), hid_seat("seat-02", "usb-x", "p2")]
        )


def test_table_rejects_a_by_path_claimed_by_two_seats():
    with pytest.raises(ValidationError):
        SeatTable(
            seats=[hid_seat("seat-01", "usb-a", "p1"), hid_seat("seat-02", "usb-b", "p1")]
        )


def test_table_rejects_a_by_id_used_twice_within_one_seat():
    seat = SeatSpec(
        profile=profile(),
        devices={HID: DeviceMatch(by_id="usb-x"), CARD: DeviceMatch(by_id="usb-x")},
    )
    with pytest.raises(ValidationError):
        SeatTable(seats=[seat])


# ---- Roles, status, state, change ------------------------------------------

def test_role_values():
    assert [r.value for r in DeviceRole] == ["hid_board", "capture_card", "phone"]


def test_seat_status_values():
    assert [s.value for s in SeatStatus] == ["absent", "partial", "ready", "conflict"]


def test_state_defaults_to_no_devices():
    state = SeatState(seat_id="seat-01", status=SeatStatus.ABSENT)
    assert state.present == frozenset()
    assert state.conflicted == frozenset()
    assert state.ready_modes == frozenset()


def test_state_accepts_ready_modes():
    state = SeatState(
        seat_id="seat-01",
        status=SeatStatus.PARTIAL,
        ready_modes=frozenset({InputMode.ADB}),
    )
    assert state.ready_modes == frozenset({InputMode.ADB})


def test_state_rejects_blank_seat_id():
    with pytest.raises(ValidationError):
        SeatState(seat_id="  ", status=SeatStatus.ABSENT)


def test_change_rejects_a_no_op():
    with pytest.raises(ValidationError):
        SeatChange(seat_id="seat-01", before=SeatStatus.READY, after=SeatStatus.READY)


def test_change_accepts_a_transition():
    change = SeatChange(
        seat_id="seat-01", before=SeatStatus.ABSENT, after=SeatStatus.PARTIAL
    )
    assert (change.before, change.after) == (SeatStatus.ABSENT, SeatStatus.PARTIAL)
    assert change.ready_modes_before == frozenset()
    assert change.ready_modes_after == frozenset()


def test_change_accepts_same_status_when_modes_change():
    change = SeatChange(
        seat_id="seat-01",
        before=SeatStatus.PARTIAL,
        after=SeatStatus.PARTIAL,
        ready_modes_after=frozenset({InputMode.ADB}),
    )
    assert change.ready_modes_after == frozenset({InputMode.ADB})


def test_change_rejects_a_no_op_even_when_modes_match():
    with pytest.raises(ValidationError):
        SeatChange(
            seat_id="seat-01",
            before=SeatStatus.READY,
            after=SeatStatus.READY,
            ready_modes_before=frozenset({InputMode.HID}),
            ready_modes_after=frozenset({InputMode.HID}),
        )
