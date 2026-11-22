"""W1 exit demo: a virtual device attaches and detaches through the real registry."""
import pytest

from farm.contracts.events import DeviceEventKind, DeviceEventSource
from farm.contracts.models import DeviceProfile, InputMode
from farm.contracts.seats import (
    DeviceMatch,
    DeviceRole,
    SeatSpec,
    SeatStatus,
    SeatTable,
)
from farm.registry import SeatRegistry
from farm.testing.clock import FakeClock
from farm.testing.sim_device import SimDevice

HID = DeviceRole.HID_BOARD
CARD = DeviceRole.CAPTURE_CARD
PHONE = DeviceRole.PHONE


def spec(seat_id="seat-01", modes=(InputMode.HID,), devices=None):
    if devices is None:
        devices = {HID: DeviceMatch(by_id="ctrl"), CARD: DeviceMatch(by_path="p1")}
    return SeatSpec(
        profile=DeviceProfile(device_id=seat_id, input_modes=list(modes)),
        devices=devices,
    )


def standard():
    return spec()


def adb_only():
    return spec(
        "seat-02",
        (InputMode.ADB,),
        {PHONE: DeviceMatch(by_id="phone", by_path="p2")},
    )


def drain(registry, sim):
    """Apply every queued event through the real registry (no early close)."""
    return [c for event in sim.source.events() for c in registry.apply(event)]


# ---- The W1 exit demo -------------------------------------------------------


def test_virtual_device_attaches_and_detaches_through_the_real_registry():
    seat = standard()
    registry = SeatRegistry(SeatTable(seats=[seat]))
    sim = SimDevice(seat)

    assert [c.after for c in drain(registry, sim)] == []
    assert registry.state(seat.seat_id).status is SeatStatus.ABSENT

    attach_events = sim.attach()
    assert len(attach_events) == 2
    assert [c.after for c in drain(registry, sim)] == [
        SeatStatus.PARTIAL,
        SeatStatus.READY,
    ]
    assert registry.state(seat.seat_id).status is SeatStatus.READY

    detach_events = sim.detach()
    assert len(detach_events) == 2
    assert [c.after for c in drain(registry, sim)] == [
        SeatStatus.PARTIAL,
        SeatStatus.ABSENT,
    ]
    assert registry.state(seat.seat_id).status is SeatStatus.ABSENT


def test_adb_only_seat_attaches_and_detaches():
    seat = adb_only()
    registry = SeatRegistry(SeatTable(seats=[seat]))
    sim = SimDevice(seat)

    sim.attach()
    assert [c.after for c in drain(registry, sim)] == [SeatStatus.READY]
    sim.detach()
    assert [c.after for c in drain(registry, sim)] == [SeatStatus.ABSENT]


def test_partial_attach_then_complete():
    seat = standard()
    registry = SeatRegistry(SeatTable(seats=[seat]))
    sim = SimDevice(seat)

    sim.attach([HID])
    assert [c.after for c in drain(registry, sim)] == [SeatStatus.PARTIAL]
    sim.attach([CARD])
    assert [c.after for c in drain(registry, sim)] == [SeatStatus.READY]


def test_restart_with_devices_already_present_reaches_ready_without_new_events():
    # N1: a restarted host sees the already-plugged devices at iteration start.
    seat = standard()
    registry = SeatRegistry(SeatTable(seats=[seat]))
    sim = SimDevice(seat, present=list(seat.devices))

    assert [c.after for c in drain(registry, sim)] == [
        SeatStatus.PARTIAL,
        SeatStatus.READY,
    ]
    assert registry.state(seat.seat_id).status is SeatStatus.READY


def test_seats_are_independent():
    first, second = standard(), adb_only()
    registry = SeatRegistry(SeatTable(seats=[first, second]))
    sim = SimDevice(first)

    sim.attach()
    drain(registry, sim)
    assert registry.state(first.seat_id).status is SeatStatus.READY
    assert registry.state(second.seat_id).status is SeatStatus.ABSENT


# ---- Event shape ------------------------------------------------------------


def test_attach_events_are_udev_shaped_and_monotonic():
    seat = standard()
    clock = FakeClock(start_ns=500)
    sim = SimDevice(seat, clock)

    events = sim.attach()
    assert all(e.kind is DeviceEventKind.ATTACHED for e in events)
    assert [e.observed_ns for e in events] == sorted(e.observed_ns for e in events)
    assert all(e.observed_ns >= 500 for e in events)
    assert all(len(e.vendor_id) == 4 and len(e.product_id) == 4 for e in events)
    assert {e.by_path for e in events} == {None, "p1"}


def test_detach_keeps_the_identity_but_changes_kind_and_timestamp():
    seat = standard()
    sim = SimDevice(seat)
    attached = sim.attach()
    detached = sim.detach()

    identity = ("by_id", "by_path", "serial", "vendor_id", "product_id")
    for before, after in zip(attached, reversed(detached)):
        assert before.kind is DeviceEventKind.ATTACHED
        assert after.kind is DeviceEventKind.DETACHED
        assert all(getattr(before, f) == getattr(after, f) for f in identity)
        assert after.observed_ns > before.observed_ns


def test_detached_events_leave_no_state_behind():
    seat = standard()
    registry = SeatRegistry(SeatTable(seats=[seat]))
    sim = SimDevice(seat)
    sim.attach()
    sim.detach()
    changes = drain(registry, sim)
    assert [c.after for c in changes] == [
        SeatStatus.PARTIAL,
        SeatStatus.READY,
        SeatStatus.PARTIAL,
        SeatStatus.ABSENT,
    ]
    assert registry.state(seat.seat_id).status is SeatStatus.ABSENT


# ---- Sim device API ---------------------------------------------------------


def test_attach_twice_is_rejected():
    sim = SimDevice(standard())
    sim.attach([HID])
    with pytest.raises(ValueError):
        sim.attach([HID])


def test_duplicate_role_in_one_batch_is_rejected():
    sim = SimDevice(standard())
    with pytest.raises(ValueError):
        sim.attach([HID, HID])
    assert list(sim.source.events()) == []


def test_failed_attach_is_atomic():
    # CR-7b: validate every role before attaching any, so a rejected batch
    # leaves neither queued events nor partial state behind.
    sim = SimDevice(standard())
    sim.attach([CARD])
    assert len(list(sim.source.events())) == 1  # drain the successful attach

    with pytest.raises(ValueError):
        sim.attach([HID, CARD])  # CARD is already attached

    assert list(sim.source.events()) == []
    assert len(sim.detach()) == 1  # only the original CARD was ever attached


def test_unknown_role_is_rejected():
    sim = SimDevice(standard())
    with pytest.raises(KeyError):
        sim.attach(["usb_hub"])


def test_detach_before_attach_emits_nothing():
    sim = SimDevice(standard())
    assert sim.detach() == ()


def test_close_closes_the_feed():
    sim = SimDevice(standard())
    sim.close()
    assert sim.source.closed is True


def test_source_satisfies_the_device_event_source_seam():
    sim = SimDevice(standard())
    assert isinstance(sim.source, DeviceEventSource)
