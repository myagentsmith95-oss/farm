"""Seat resolution: turn device events into seat state transitions.

The registry is inventory, not lease authority and not the event log. It keeps
the identities currently claiming each role, so a second device at the same
physical port is a conflict rather than a silent replacement. SeatStatus and
SeatChange are derived from those claims; no status is stored on its own.
"""
from dataclasses import dataclass, field

from farm.contracts.events import DeviceEvent, DeviceEventKind, DeviceEventSource
from farm.contracts.seats import (
    DeviceRole,
    SeatChange,
    SeatSpec,
    SeatState,
    SeatStatus,
    SeatTable,
)


@dataclass(frozen=True)
class _Identity:
    """Which device occupies a role. Timestamps and event kind are not identity."""

    by_id: str
    by_path: str | None
    serial: str | None

    @classmethod
    def from_event(cls, event: DeviceEvent) -> "_Identity":
        return cls(event.by_id, event.by_path, event.serial)


@dataclass
class _Occupancy:
    claims: dict[DeviceRole, set[_Identity]] = field(default_factory=dict)


class SeatRegistry:
    """Resolves attach/detach events against an enrollment table of seats."""

    def __init__(self, table: SeatTable) -> None:
        self._table = table
        self._specs = {seat.seat_id: seat for seat in table.seats}
        self._occupancy = {seat.seat_id: _Occupancy() for seat in table.seats}

    def state(self, seat_id: str) -> SeatState:
        return self._snapshot(self._specs[seat_id], self._occupancy[seat_id])

    def states(self) -> tuple[SeatState, ...]:
        return tuple(self.state(seat.seat_id) for seat in self._table.seats)

    def apply(self, event: DeviceEvent) -> tuple[SeatChange, ...]:
        """Apply one event, returning the status transitions it caused."""
        changes: list[SeatChange] = []
        identity = _Identity.from_event(event)
        for seat in self._table.seats:
            occupancy = self._occupancy[seat.seat_id]
            before = self._snapshot(seat, occupancy).status
            for role, match in seat.devices.items():
                if not match.matches(event):
                    continue
                claims = occupancy.claims.setdefault(role, set())
                if event.kind is DeviceEventKind.ATTACHED:
                    claims.add(identity)
                else:
                    claims.discard(identity)
                    if not claims:
                        del occupancy.claims[role]
            after = self._snapshot(seat, occupancy).status
            if before is not after:
                changes.append(SeatChange(seat_id=seat.seat_id, before=before, after=after))
        return tuple(changes)

    @staticmethod
    def _snapshot(spec: SeatSpec, occupancy: _Occupancy) -> SeatState:
        present = frozenset(
            role for role, claims in occupancy.claims.items() if len(claims) == 1
        )
        conflicted = frozenset(
            role for role, claims in occupancy.claims.items() if len(claims) > 1
        )
        required = set(spec.devices)
        if conflicted:
            status = SeatStatus.CONFLICT
        elif present == required:
            status = SeatStatus.READY
        elif present:
            status = SeatStatus.PARTIAL
        else:
            status = SeatStatus.ABSENT
        return SeatState(
            seat_id=spec.seat_id,
            status=status,
            present=present,
            conflicted=conflicted,
        )


def resolve_all(
    registry: SeatRegistry, source: DeviceEventSource
) -> tuple[SeatChange, ...]:
    """Drain a finite event source (fake feeds and CI) through the registry.

    A live udev source blocks forever; callers with an unbounded source should
    iterate source.events() and call apply() themselves instead.
    """
    changes: list[SeatChange] = []
    try:
        for event in source.events():
            changes.extend(registry.apply(event))
    finally:
        source.close()
    return tuple(changes)
