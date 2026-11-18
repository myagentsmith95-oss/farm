"""Seat resolution: DeviceEvents -> SeatState transitions."""
import pytest
from hypothesis import given, settings, strategies as st

from farm.contracts.events import DeviceEvent, DeviceEventKind, DeviceEventSource
from farm.contracts.models import DeviceProfile, InputMode
from farm.contracts.seats import DeviceMatch, DeviceRole, SeatChange, SeatSpec, SeatState, SeatStatus, SeatTable
from farm.registry import SeatRegistry, resolve_all


def change(seat, before, after):
    return SeatChange(seat_id=seat, before=before, after=after)


def state(seat, status, present=frozenset(), conflicted=frozenset()):
    return SeatState(seat_id=seat, status=status, present=present, conflicted=conflicted)


HID = DeviceRole.HID_CONTROLLER
CARD = DeviceRole.CAPTURE_CARD
PHONE = DeviceRole.PHONE


def spec(seat_id, modes, devices):
    return SeatSpec(
        profile=DeviceProfile(device_id=seat_id, input_modes=list(modes)),
        devices=devices,
    )


def table():
    return SeatTable(
        seats=[
            spec("std", (InputMode.HID,), {HID: DeviceMatch(by_id="ctrl"), CARD: DeviceMatch(by_path="p1")}),
            spec("adb", (InputMode.ADB,), {PHONE: DeviceMatch(by_id="phone")}),
            spec(
                "both",
                (InputMode.HID, InputMode.ADB),
                {
                    HID: DeviceMatch(by_id="ctrl2"),
                    PHONE: DeviceMatch(by_id="phone2"),
                    CARD: DeviceMatch(by_path="p3"),
                },
            ),
        ]
    )


def event(kind, by_id="x", by_path=None, serial=None):
    return DeviceEvent(
        kind=kind,
        by_id=by_id,
        by_path=by_path,
        vendor_id="303a",
        product_id="1001",
        serial=serial,
        observed_ns=1,
    )


ATTACH = DeviceEventKind.ATTACHED
DETACH = DeviceEventKind.DETACHED


def changes(registry, *events):
    return [change for e in events for change in registry.apply(e)]


# ---- Profile store / registry construction ---------------------------------


def test_registry_starts_all_seats_absent():
    registry = SeatRegistry(table())
    assert [(s.seat_id, s.status) for s in registry.states()] == [
        ("std", SeatStatus.ABSENT),
        ("adb", SeatStatus.ABSENT),
        ("both", SeatStatus.ABSENT),
    ]


def test_unknown_seat_id_raises_key_error():
    with pytest.raises(KeyError):
        SeatRegistry(table()).state("missing")


def test_states_are_snapshots():
    registry = SeatRegistry(table())
    before = registry.states()
    registry.apply(event(ATTACH, "ctrl"))
    assert before == (
        state("std", SeatStatus.ABSENT),
        state("adb", SeatStatus.ABSENT),
        state("both", SeatStatus.ABSENT),
    )


# ---- Standard seat lifecycle ------------------------------------------------


def test_standard_seat_absent_to_partial_to_ready_and_back():
    registry = SeatRegistry(table())
    assert changes(registry, event(ATTACH, "ctrl")) == [
        change("std", SeatStatus.ABSENT, SeatStatus.PARTIAL)
    ]
    assert registry.state("std") == state("std", SeatStatus.PARTIAL, frozenset({HID}))

    assert changes(registry, event(ATTACH, "ignored", "p1")) == [
        change("std", SeatStatus.PARTIAL, SeatStatus.READY)
    ]
    assert registry.state("std") == state("std", SeatStatus.READY, frozenset({HID, CARD}))

    assert changes(registry, event(DETACH, "ignored", "p1")) == [
        change("std", SeatStatus.READY, SeatStatus.PARTIAL)
    ]
    assert changes(registry, event(DETACH, "ctrl")) == [
        change("std", SeatStatus.PARTIAL, SeatStatus.ABSENT)
    ]
    assert registry.state("std") == state("std", SeatStatus.ABSENT)


def test_adb_only_seat_goes_ready_on_phone_attach():
    registry = SeatRegistry(table())
    assert changes(registry, event(ATTACH, "phone")) == [
        change("adb", SeatStatus.ABSENT, SeatStatus.READY)
    ]
    assert registry.state("adb") == state("adb", SeatStatus.READY, frozenset({PHONE}))


def test_dual_mode_seat_transitions_through_all_states():
    registry = SeatRegistry(table())
    assert changes(registry, event(ATTACH, "ctrl2")) == [
        change("both", SeatStatus.ABSENT, SeatStatus.PARTIAL)
    ]
    assert changes(registry, event(ATTACH, "phone2")) == []
    assert registry.state("both").status is SeatStatus.PARTIAL
    assert changes(registry, event(ATTACH, "card", "p3")) == [
        change("both", SeatStatus.PARTIAL, SeatStatus.READY)
    ]


# ---- Matching rules ---------------------------------------------------------


def test_unknown_device_is_ignored():
    registry = SeatRegistry(table())
    assert changes(registry, event(ATTACH, "unknown", "unknown")) == []
    assert registry.states() == tuple(
        state(s.seat_id, SeatStatus.ABSENT) for s in table().seats
    )


def test_by_path_match_ignores_the_event_id():
    registry = SeatRegistry(table())
    registry.apply(event(ATTACH, "anything", "p1"))
    assert registry.state("std").present == frozenset({CARD})


def test_by_id_match_ignores_a_non_matching_path():
    registry = SeatRegistry(table())
    registry.apply(event(ATTACH, "ctrl", "some-other-port"))
    assert registry.state("std").present == frozenset({HID})


def test_both_identifiers_must_agree():
    spec_both = SeatSpec(
        profile=DeviceProfile(device_id="strict", input_modes=[InputMode.HID]),
        devices={HID: DeviceMatch(by_id="ctrl", by_path="p9")},
    )
    registry = SeatRegistry(SeatTable(seats=[spec_both]))
    assert changes(registry, event(ATTACH, "ctrl", "wrong")) == []
    assert changes(registry, event(ATTACH, "wrong", "p9")) == []
    assert changes(registry, event(ATTACH, "ctrl", "p9")) == [
        change("strict", SeatStatus.ABSENT, SeatStatus.READY)
    ]


# ---- Conflicts and duplicate events ----------------------------------------


def test_second_device_claiming_a_role_raises_conflict():
    registry = SeatRegistry(table())
    changes(registry, event(ATTACH, "ctrl"))
    changes(registry, event(ATTACH, "card", "p1", serial="original"))
    assert changes(registry, event(ATTACH, "other", "p1", serial="other-card")) == [
        change("std", SeatStatus.READY, SeatStatus.CONFLICT)
    ]
    assert registry.state("std") == state(
        "std", SeatStatus.CONFLICT, frozenset({HID}), frozenset({CARD})
    )


def test_conflict_clears_when_the_intruder_detaches():
    registry = SeatRegistry(table())
    changes(registry, event(ATTACH, "ctrl"))
    changes(registry, event(ATTACH, "ignored", "p1"))
    changes(registry, event(ATTACH, "other", "p1", serial="extra"))
    assert registry.state("std").status is SeatStatus.CONFLICT
    assert changes(registry, event(DETACH, "other", "p1", serial="extra")) == [
        change("std", SeatStatus.CONFLICT, SeatStatus.READY)
    ]


def test_conflict_persists_until_every_extra_claimant_leaves():
    registry = SeatRegistry(table())
    changes(registry, event(ATTACH, "ctrl"))
    changes(registry, event(ATTACH, "card", "p1", serial="original"))
    changes(registry, event(ATTACH, "one", "p1", serial="one"))
    changes(registry, event(ATTACH, "two", "p1", serial="two"))
    assert registry.state("std").status is SeatStatus.CONFLICT
    changes(registry, event(DETACH, "one", "p1", serial="one"))
    assert registry.state("std").status is SeatStatus.CONFLICT
    changes(registry, event(DETACH, "two", "p1", serial="two"))
    assert registry.state("std").status is SeatStatus.READY


def test_duplicate_attach_is_idempotent():
    registry = SeatRegistry(table())
    changes(registry, event(ATTACH, "ctrl"))
    assert changes(registry, event(ATTACH, "ctrl")) == []
    assert registry.state("std").present == frozenset({HID})


def test_detach_of_a_non_claimant_is_a_no_op():
    registry = SeatRegistry(table())
    assert changes(registry, event(DETACH, "ctrl")) == []
    changes(registry, event(ATTACH, "ctrl", serial="real"))
    assert changes(registry, event(DETACH, "ctrl", serial="different")) == []
    assert registry.state("std").status is SeatStatus.PARTIAL


def test_detaching_the_occupant_then_attaching_again_reuses_the_role():
    registry = SeatRegistry(table())
    changes(registry, event(ATTACH, "ctrl"))
    changes(registry, event(DETACH, "ctrl"))
    assert changes(registry, event(ATTACH, "ctrl")) == [
        change("std", SeatStatus.ABSENT, SeatStatus.PARTIAL)
    ]


def test_one_event_can_move_two_seats():
    # A by_id that collides with another seat's by_path namespace.
    crossed = SeatTable(
        seats=[
            spec("a", (InputMode.HID,), {HID: DeviceMatch(by_id="shared")}),
            spec("b", (InputMode.HID,), {HID: DeviceMatch(by_path="shared")}),
        ]
    )
    registry = SeatRegistry(crossed)
    assert changes(registry, event(ATTACH, "shared", "shared")) == [
        change("a", SeatStatus.ABSENT, SeatStatus.READY),
        change("b", SeatStatus.ABSENT, SeatStatus.READY),
    ]


# ---- Finite feed integration ------------------------------------------------


def test_resolve_all_drains_a_fake_feed_and_closes_it():
    from farm.testing.events import FakeDeviceEventSource

    feed = FakeDeviceEventSource()
    feed.push(event(ATTACH, "ctrl"))
    feed.push(event(ATTACH, "ignored", "p1"))
    registry = SeatRegistry(table())
    assert resolve_all(registry, feed) == (
        change("std", SeatStatus.ABSENT, SeatStatus.PARTIAL),
        change("std", SeatStatus.PARTIAL, SeatStatus.READY),
    )
    assert feed.closed is True


# ---- Property: status is always derivable from present/conflicted -----------

hex4 = st.text(alphabet="0123456789abcdef", min_size=4, max_size=4)
ids = st.sampled_from(["ctrl", "card", "phone", "ctrl2", "phone2", "intruder"])
paths = st.sampled_from(["p1", "p3", "p9", "other-port"])
event_strategy = st.builds(
    DeviceEvent,
    kind=st.sampled_from(list(DeviceEventKind)),
    by_id=ids,
    by_path=st.one_of(st.none(), paths),
    vendor_id=hex4,
    product_id=hex4,
    serial=st.one_of(st.none(), st.sampled_from(["a", "b"])),
    observed_ns=st.integers(min_value=0, max_value=1000),
)


@settings(max_examples=150)
@given(st.lists(event_strategy, max_size=15))
def test_status_is_consistent_with_occupancy_after_any_event_stream(events):
    t = table()
    registry = SeatRegistry(t)
    for e in events:
        registry.apply(e)
        for seat in t.seats:
            state = registry.state(seat.seat_id)
            required = set(seat.devices)
            assert state.present <= required
            assert state.conflicted <= required
            assert not (state.present & state.conflicted)
            if state.conflicted:
                assert state.status is SeatStatus.CONFLICT
            elif state.present == required:
                assert state.status is SeatStatus.READY
            elif state.present:
                assert state.status is SeatStatus.PARTIAL
            else:
                assert state.status is SeatStatus.ABSENT


def test_registry_only_uses_the_event_source_seam():
    # A compile-time/interface check: FakeDeviceEventSource satisfies the seam.
    from farm.testing.events import FakeDeviceEventSource

    source: DeviceEventSource = FakeDeviceEventSource()
    assert isinstance(source, DeviceEventSource)
