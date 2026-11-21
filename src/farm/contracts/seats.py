"""Seat models. PROVISIONAL: revisit when the registry core is written.

A seat is one phone plus the hardware around it. The registry (inventory, not
leases) matches attach and detach events against an enrollment table of
SeatSpecs. Roles name the hardware, not the function: a seat that lists hid
input needs a hid_board, one that lists adb input needs a phone.
"""
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from farm.contracts.events import DeviceEvent
from farm.contracts.models import DeviceProfile, InputMode

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DeviceRole(StrEnum):
    """The physical thing that must be recognised at a seat."""

    HID_BOARD = "hid_board"  # ESP32-S3 USB HID board
    CAPTURE_CARD = "capture_card"  # UVC / HDMI capture card
    PHONE = "phone"  # the phone itself, for the ADB path


# The single rulebook for what hardware an input mode needs. Both enrollment
# (SeatSpec) and readiness (the registry) use it, so they cannot drift apart.
MODE_ROLES: dict[InputMode, frozenset[DeviceRole]] = {
    InputMode.HID: frozenset({DeviceRole.HID_BOARD, DeviceRole.CAPTURE_CARD}),
    InputMode.ADB: frozenset({DeviceRole.PHONE}),
}


class SeatStatus(StrEnum):
    ABSENT = "absent"  # no required device present
    PARTIAL = "partial"  # some required devices present
    READY = "ready"  # every required device present
    CONFLICT = "conflict"  # a second device claims an already-filled role


class DeviceMatch(_Model):
    """How to recognise a device. by_id survives moving a board between ports;
    by_path pins a physical USB port, for cards with no unique serial. When both
    are given, both must agree."""

    by_id: NonBlank | None = None
    by_path: NonBlank | None = None

    @model_validator(mode="after")
    def _has_an_identifier(self) -> "DeviceMatch":
        if self.by_id is None and self.by_path is None:
            raise ValueError("a match needs by_id, by_path, or both")
        return self

    def matches(self, event: DeviceEvent) -> bool:
        if self.by_id is not None and event.by_id != self.by_id:
            return False
        if self.by_path is not None and event.by_path != self.by_path:
            return False
        return True


class SeatSpec(_Model):
    """One enrolled seat. The seat id is the profile's device id."""

    profile: DeviceProfile
    devices: Annotated[dict[DeviceRole, DeviceMatch], Field(min_length=1)]

    @property
    def seat_id(self) -> str:
        return self.profile.device_id

    @model_validator(mode="after")
    def _roles_support_input_modes(self) -> "SeatSpec":
        # At least one declared mode must have all its required roles. A
        # dual-mode seat with no capture card is still a valid ADB seat;
        # rejecting it would lose phones that have no video output.
        available = set(self.devices)
        if not any(MODE_ROLES[mode] <= available for mode in self.profile.input_modes):
            raise ValueError("at least one input mode must have all its required roles")
        return self


class SeatTable(_Model):
    """The enrollment table: every seat the farm knows about."""

    seats: Annotated[tuple[SeatSpec, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _identifiers_are_unique(self) -> "SeatTable":
        seat_ids = [seat.seat_id for seat in self.seats]
        if len(set(seat_ids)) != len(seat_ids):
            raise ValueError("duplicate seat id")
        matches = [m for seat in self.seats for m in seat.devices.values()]
        by_ids = [m.by_id for m in matches if m.by_id is not None]
        by_paths = [m.by_path for m in matches if m.by_path is not None]
        if len(set(by_ids)) != len(by_ids):
            raise ValueError("a by_id is claimed more than once")
        if len(set(by_paths)) != len(by_paths):
            raise ValueError("a by_path is claimed more than once")
        return self


class SeatState(_Model):
    """Inventory snapshot. status/present describe which hardware is plugged
    in; ready_modes answers the scheduler's question — which input modes are
    usable right now. A PARTIAL seat can still be usable via a fallback mode.

    CONFLICT removes only the modes whose required roles are conflicted; modes
    whose roles remain present stay usable. ready_modes is therefore computed
    per mode and is not a restatement of status — schedulers must consult it
    rather than gating on status alone."""

    seat_id: NonBlank
    status: SeatStatus
    present: frozenset[DeviceRole] = frozenset()
    conflicted: frozenset[DeviceRole] = frozenset()
    ready_modes: frozenset[InputMode] = frozenset()


class SeatChange(_Model):
    """One observable seat transition. A status that does not move can still be
    a change when the set of usable input modes does. Consumers (the scheduler,
    the event stream) must read the mode fields, not just before/after status."""

    seat_id: NonBlank
    before: SeatStatus
    after: SeatStatus
    ready_modes_before: frozenset[InputMode] = frozenset()
    ready_modes_after: frozenset[InputMode] = frozenset()

    @model_validator(mode="after")
    def _is_a_real_change(self) -> "SeatChange":
        if self.before == self.after and self.ready_modes_before == self.ready_modes_after:
            raise ValueError("a change must move the status or the usable modes")
        return self
