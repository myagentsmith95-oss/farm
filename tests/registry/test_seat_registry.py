"""Seat resolution: DeviceEvents -> SeatState transitions."""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from farm.contracts.events import DeviceEvent, DeviceEventKind, DeviceEventSource
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
from farm.registry import SeatRegistry, resolve_all


def change(seat, before, after, modes_before=frozenset(), modes_after=frozenset()):
    return SeatChange(
        seat_id=seat,
        before=before,
        after=after,
        ready_modes_before=modes_before,
        ready_modes_after=modes_after,
    )


HID = DeviceRole.HID_BOARD
CARD = DeviceRole.CAPTURE_CARD
PHONE = DeviceRole.PHONE

def state(seat, status, present=frozenset(), conflicted=frozenset(), ready_modes=frozenset()):
    # ready_modes is always an explicit literal: deriving it from `present`
    # here would re-encode production's formula and make equality tests
    # self-confirming (review v4, T2).
    return SeatState(
        seat_id=seat,
        status=status,
        present=present,
        conflicted=conflicted,
        ready_modes=ready_modes,
    )


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


def test_registry_does_not_alias_the_enrollment_table():
    t = SeatTable(
        seats=[
            spec(
                "std",
                (InputMode.HID,),
                {HID: DeviceMatch(by_id="ctrl"), CARD: DeviceMatch(by_path="p1")},
            )
        ]
    )
    registry = SeatRegistry(t)
    before = registry.states()
    t.seats[0].devices.clear()  # SeatSpec is frozen; the devices dict is not
    assert registry.states() == before


# ---- Standard seat lifecycle ------------------------------------------------


def test_standard_seat_absent_to_partial_to_ready_and_back():
    registry = SeatRegistry(table())
    assert changes(registry, event(ATTACH, "ctrl")) == [
        change("std", SeatStatus.ABSENT, SeatStatus.PARTIAL)
    ]
    assert registry.state("std") == state("std", SeatStatus.PARTIAL, frozenset({HID}))

    assert changes(registry, event(ATTACH, "ignored", "p1")) == [
        change(
            "std",
            SeatStatus.PARTIAL,
            SeatStatus.READY,
            modes_after=frozenset({InputMode.HID}),
        )
    ]
    assert registry.state("std") == state(
        "std", SeatStatus.READY, frozenset({HID, CARD}), ready_modes=frozenset({InputMode.HID})
    )

    assert changes(registry, event(DETACH, "ignored", "p1")) == [
        change(
            "std",
            SeatStatus.READY,
            SeatStatus.PARTIAL,
            modes_before=frozenset({InputMode.HID}),
        )
    ]
    assert changes(registry, event(DETACH, "ctrl")) == [
        change("std", SeatStatus.PARTIAL, SeatStatus.ABSENT)
    ]
    assert registry.state("std") == state("std", SeatStatus.ABSENT)


def test_adb_only_seat_goes_ready_on_phone_attach():
    registry = SeatRegistry(table())
    assert changes(registry, event(ATTACH, "phone")) == [
        change("adb", SeatStatus.ABSENT, SeatStatus.READY, modes_after=frozenset({InputMode.ADB}))
    ]
    assert registry.state("adb") == state(
        "adb", SeatStatus.READY, frozenset({PHONE}), ready_modes=frozenset({InputMode.ADB})
    )


def test_dual_mode_seat_transitions_through_all_states():
    registry = SeatRegistry(table())
    assert changes(registry, event(ATTACH, "ctrl2")) == [
        change("both", SeatStatus.ABSENT, SeatStatus.PARTIAL)
    ]
    assert changes(registry, event(ATTACH, "phone2")) == [
        change(
            "both",
            SeatStatus.PARTIAL,
            SeatStatus.PARTIAL,
            modes_after=frozenset({InputMode.ADB}),
        )
    ]
    assert registry.state("both").status is SeatStatus.PARTIAL
    assert changes(registry, event(ATTACH, "card", "p3")) == [
        change(
            "both",
            SeatStatus.PARTIAL,
            SeatStatus.READY,
            modes_before=frozenset({InputMode.ADB}),
            modes_after=frozenset({InputMode.HID, InputMode.ADB}),
        )
    ]


def test_dual_mode_seat_reports_adb_ready_when_only_the_phone_is_attached():
    # N2: PARTIAL is inventory completeness, not "unusable". ADB needs only the
    # phone, so the fallback must be schedulable even with the board unplugged.
    registry = SeatRegistry(table())
    registry.apply(event(ATTACH, "phone2"))
    state = registry.state("both")
    assert state.status is SeatStatus.PARTIAL
    assert state.ready_modes == frozenset({InputMode.ADB})


def test_hid_ready_modes_require_the_capture_card():
    # R2: HID input alone cannot close the capture-recognise-act-verify loop.
    registry = SeatRegistry(table())
    registry.apply(event(ATTACH, "ctrl"))
    assert registry.state("std").ready_modes == frozenset()
    registry.apply(event(ATTACH, "ignored", "p1"))
    assert registry.state("std").ready_modes == frozenset({InputMode.HID})


def test_ready_modes_is_empty_for_absent_and_conflicted_seats():
    registry = SeatRegistry(table())
    assert registry.state("adb").ready_modes == frozenset()
    registry.apply(event(ATTACH, "ctrl", "p1"))
    assert registry.state("std").status is SeatStatus.CONFLICT
    assert registry.state("std").ready_modes == frozenset()


def test_conflict_removes_only_the_modes_whose_roles_are_conflicted():
    # R3: a contested PHONE removes ADB but leaves the fully present HID path
    # usable. ready_modes is per-mode, not a restatement of status.
    registry = SeatRegistry(table())
    registry.apply(event(ATTACH, "ctrl2"))
    registry.apply(event(ATTACH, "ignored", "p3"))
    registry.apply(event(ATTACH, "phone2", serial="a"))
    registry.apply(event(ATTACH, "phone2", serial="b"))
    state = registry.state("both")
    assert state.status is SeatStatus.CONFLICT
    assert state.conflicted == frozenset({PHONE})
    assert state.present == frozenset({HID, CARD})
    assert state.ready_modes == frozenset({InputMode.HID})


def test_detach_of_the_last_mode_emits_a_change_with_the_same_status():
    # CR-1: the scheduler hears about a usable mode disappearing even when
    # inventory status does not move.
    registry = SeatRegistry(table())
    registry.apply(event(ATTACH, "phone2"))
    registry.apply(event(ATTACH, "ignored", "p3"))
    assert registry.state("both").status is SeatStatus.PARTIAL
    assert registry.state("both").ready_modes == frozenset({InputMode.ADB})

    assert changes(registry, event(DETACH, "phone2")) == [
        change(
            "both",
            SeatStatus.PARTIAL,
            SeatStatus.PARTIAL,
            modes_before=frozenset({InputMode.ADB}),
        )
    ]


def test_conflict_resolution_emits_a_ready_modes_change():
    # The capture card is attached too: under MODE_ROLES, HID needs board+card.
    registry = SeatRegistry(table())
    registry.apply(event(ATTACH, "ctrl2", serial="a"))
    registry.apply(event(ATTACH, "ctrl2", serial="b"))
    registry.apply(event(ATTACH, "phone2", serial="a"))
    registry.apply(event(ATTACH, "phone2", serial="b"))
    registry.apply(event(ATTACH, "card", "p3"))
    assert registry.state("both").status is SeatStatus.CONFLICT
    assert registry.state("both").ready_modes == frozenset()

    assert changes(registry, event(DETACH, "ctrl2", serial="a")) == [
        change(
            "both",
            SeatStatus.CONFLICT,
            SeatStatus.CONFLICT,
            modes_after=frozenset({InputMode.HID}),
        )
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
        profile=DeviceProfile(device_id="strict", input_modes=[InputMode.ADB]),
        devices={PHONE: DeviceMatch(by_id="ctrl", by_path="p9")},
    )
    registry = SeatRegistry(SeatTable(seats=[spec_both]))
    assert changes(registry, event(ATTACH, "ctrl", "wrong")) == []
    assert changes(registry, event(ATTACH, "wrong", "p9")) == []
    assert changes(registry, event(ATTACH, "ctrl", "p9")) == [
        change("strict", SeatStatus.ABSENT, SeatStatus.READY, modes_after=frozenset({InputMode.ADB}))
    ]


# ---- Conflicts and duplicate events ----------------------------------------


def test_second_device_claiming_a_role_raises_conflict():
    registry = SeatRegistry(table())
    changes(registry, event(ATTACH, "ctrl"))
    changes(registry, event(ATTACH, "card", "p1", serial="original"))
    assert changes(registry, event(ATTACH, "other", "p1", serial="other-card")) == [
        change(
            "std",
            SeatStatus.READY,
            SeatStatus.CONFLICT,
            modes_before=frozenset({InputMode.HID}),
        )
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
        change("std", SeatStatus.CONFLICT, SeatStatus.READY, modes_after=frozenset({InputMode.HID}))
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
            spec("a", (InputMode.ADB,), {PHONE: DeviceMatch(by_id="shared")}),
            spec("b", (InputMode.ADB,), {PHONE: DeviceMatch(by_path="shared")}),
        ]
    )
    registry = SeatRegistry(crossed)
    assert changes(registry, event(ATTACH, "shared", "shared")) == [
        change("a", SeatStatus.ABSENT, SeatStatus.READY, modes_after=frozenset({InputMode.ADB})),
        change("b", SeatStatus.ABSENT, SeatStatus.READY, modes_after=frozenset({InputMode.ADB})),
    ]


def test_one_event_cannot_fill_two_roles_of_the_same_seat():
    # M1: by_id claims the board and by_path claims the card of seat "std" in
    # one event. One physical device must not make a seat READY on its own.
    registry = SeatRegistry(table())
    assert changes(registry, event(ATTACH, "ctrl", "p1")) == [
        change("std", SeatStatus.ABSENT, SeatStatus.CONFLICT)
    ]
    assert registry.state("std").status is SeatStatus.CONFLICT
    assert registry.state("std").present == frozenset()
    assert changes(registry, event(DETACH, "ctrl", "p1")) == [
        change("std", SeatStatus.CONFLICT, SeatStatus.ABSENT)
    ]


def test_asymmetric_detach_clears_an_ambiguous_claim():
    # R1: a detach that omits the optional by_path, or matches fewer roles,
    # must still release every role the ambiguous claim occupies.
    registry = SeatRegistry(table())
    registry.apply(event(ATTACH, "ctrl", "p1", serial="s"))
    assert registry.state("std").status is SeatStatus.CONFLICT
    assert changes(registry, event(DETACH, "ctrl", serial="s")) == [
        change("std", SeatStatus.CONFLICT, SeatStatus.ABSENT)
    ]
    assert registry.state("std").status is SeatStatus.ABSENT

    # A genuinely different claimant must still be left alone.
    registry.apply(event(ATTACH, "ctrl", "p1", serial="s"))
    assert changes(registry, event(DETACH, "ctrl", serial="other")) == []
    assert registry.state("std").status is SeatStatus.CONFLICT


def _same_id_card_seat():
    return SeatSpec(
        profile=DeviceProfile(device_id="cards", input_modes=[InputMode.HID]),
        devices={HID: DeviceMatch(by_id="board"), CARD: DeviceMatch(by_id="card")},
    )


def test_id_only_detach_does_not_release_two_same_id_claims():
    # CR-3: by_id is unique per physical device, so two claims with the same
    # id mean at least one optional identifier is missing from the detach.
    registry = SeatRegistry(SeatTable(seats=[_same_id_card_seat()]))
    registry.apply(event(ATTACH, "board"))
    registry.apply(event(ATTACH, "card", serial="a"))
    registry.apply(event(ATTACH, "card", serial="b"))
    assert registry.state("cards").status is SeatStatus.CONFLICT

    registry.apply(event(DETACH, "card"))
    assert registry.state("cards").status is SeatStatus.CONFLICT
    assert registry.state("cards").conflicted == frozenset({CARD})

    # A serial-carrying detach releases only its own claim.
    registry.apply(event(DETACH, "card", serial="a"))
    assert registry.state("cards").status is SeatStatus.READY
    assert registry.state("cards").present == frozenset({HID, CARD})

    # The remaining claim can be released by an exact detach.
    registry.apply(event(DETACH, "card", serial="b"))
    assert registry.state("cards").status is SeatStatus.PARTIAL


# ---- Finite feed integration ------------------------------------------------


def test_resolve_all_drains_a_fake_feed_and_closes_it():
    from farm.testing.events import FakeDeviceEventSource

    feed = FakeDeviceEventSource()
    feed.push(event(ATTACH, "ctrl"))
    feed.push(event(ATTACH, "ignored", "p1"))
    registry = SeatRegistry(table())
    assert resolve_all(registry, feed) == (
        change("std", SeatStatus.ABSENT, SeatStatus.PARTIAL),
        change("std", SeatStatus.PARTIAL, SeatStatus.READY, modes_after=frozenset({InputMode.HID})),
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


@settings(max_examples=100)
@given(event_strategy)
def test_a_single_event_never_fills_two_roles_of_one_seat(e):
    t = table()
    registry = SeatRegistry(t)
    registry.apply(e)
    for seat in t.seats:
        assert len(registry.state(seat.seat_id).present) <= 1


def test_registry_only_uses_the_event_source_seam():
    # A compile-time/interface check: FakeDeviceEventSource satisfies the seam.
    from farm.testing.events import FakeDeviceEventSource

    source: DeviceEventSource = FakeDeviceEventSource()
    assert isinstance(source, DeviceEventSource)
