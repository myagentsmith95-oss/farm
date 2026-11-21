"""Seat resolution: turn device events into seat state transitions.

The registry is inventory, not lease authority and not the event log. It keeps
the identities currently claiming each role, so a second device at the same
physical port is a conflict rather than a silent replacement. SeatStatus and
SeatChange are derived from those claims; no status is stored on its own.
"""
from dataclasses import dataclass, field

from farm.contracts.events import DeviceEvent, DeviceEventKind, DeviceEventSource
from farm.contracts.seats import (
    MODE_ROLES,
    DeviceRole,
    SeatChange,
    SeatSpec,
    SeatState,
    SeatStatus,
    SeatTable,
)


@dataclass(frozen=True)
class _Identity:
    """Which device occupies a role. Timestamps and event kind are not identity.

    All three identifier fields are part of identity. by_id alone would cover
    most devices, but a capture card with no unique serial is matched by
    by_path: two different cards appearing at the same port must be
    distinguishable, so by_id (and serial when reported) are included too.

    Caveat: if a source reports the same device with inconsistent optional
    fields on two ATTACHes, they are treated as different claimants and the
    role goes to CONFLICT. udev normally reports these consistently. A DETACH
    with fewer optional fields releases a lone matching claim, but if several
    claims match it releases only an exact field-for-field match (CR-3).
    """

    by_id: str
    by_path: str | None
    serial: str | None

    @classmethod
    def from_event(cls, event: DeviceEvent) -> "_Identity":
        return cls(event.by_id, event.by_path, event.serial)

    def same_device(self, other: "_Identity") -> bool:
        """Every identifier both reports must agree; a missing field means
        'unspecified', not 'a different device'."""
        return (
            self.by_id == other.by_id
            and (self.by_path is None or other.by_path is None or self.by_path == other.by_path)
            and (self.serial is None or other.serial is None or self.serial == other.serial)
        )


@dataclass
class _Occupancy:
    claims: dict[DeviceRole, set[_Identity]] = field(default_factory=dict)
    # An event whose identifiers match several roles of one seat is one
    # physical device claiming them all. Record it separately so it contests
    # every matched role instead of filling them (M1).
    ambiguous: dict[DeviceRole, set[_Identity]] = field(default_factory=dict)


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
        """Apply one event, returning the status and mode transitions it caused."""
        changes: list[SeatChange] = []
        identity = _Identity.from_event(event)
        for seat in self._table.seats:
            occupancy = self._occupancy[seat.seat_id]
            before = self._snapshot(seat, occupancy)
            if event.kind is DeviceEventKind.ATTACHED:
                matched = [
                    role for role, match in seat.devices.items() if match.matches(event)
                ]
                if matched:
                    # One event is one physical device: it may claim at most one
                    # role per seat. Several matches mean an ambiguous claim, so
                    # every matched role is contested rather than filled.
                    targets = occupancy.ambiguous if len(matched) > 1 else occupancy.claims
                    for role in matched:
                        targets.setdefault(role, set()).add(identity)
            else:
                # C27: release a lone matching claim even if the detach omits
                # optional identifiers. CR-3: if several claims match, they
                # cannot all be the departing device (by_id is unique per
                # physical device), so release only an exact field-for-field
                # match. No exact match means stay CONFLICT until one arrives.
                for targets in (occupancy.claims, occupancy.ambiguous):
                    for role in list(targets):
                        claims = targets[role]
                        matches = [c for c in claims if c.same_device(identity)]
                        if not matches:
                            continue
                        if len(matches) == 1:
                            claims.difference_update(matches)
                        else:
                            claims.difference_update(c for c in matches if c == identity)
                        if not claims:
                            del targets[role]
            after = self._snapshot(seat, occupancy)
            if before.status is not after.status or before.ready_modes != after.ready_modes:
                changes.append(
                    SeatChange(
                        seat_id=seat.seat_id,
                        before=before.status,
                        after=after.status,
                        ready_modes_before=before.ready_modes,
                        ready_modes_after=after.ready_modes,
                    )
                )
        return tuple(changes)

    @staticmethod
    def _snapshot(spec: SeatSpec, occupancy: _Occupancy) -> SeatState:
        contested = set(occupancy.claims) | set(occupancy.ambiguous)
        conflicted = frozenset(
            role
            for role in contested
            if len(occupancy.claims.get(role, ())) > 1 or occupancy.ambiguous.get(role)
        )
        present = frozenset(
            role
            for role, claims in occupancy.claims.items()
            if len(claims) == 1 and not occupancy.ambiguous.get(role)
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
        ready_modes = frozenset(
            mode for mode in spec.profile.input_modes if MODE_ROLES[mode] <= present
        )
        return SeatState(
            seat_id=spec.seat_id,
            status=status,
            present=present,
            conflicted=conflicted,
            ready_modes=ready_modes,
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
