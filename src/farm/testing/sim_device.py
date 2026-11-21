"""A virtual seat: hardware-shaped attach/detach events for the W1 exit demo.

SimDevice lives in farm.testing, above every production layer, so no core can
depend on it. It emits real DeviceEvents through a real DeviceEventSource; the
registry under test is the production SeatRegistry, not a mock. No udev or
hardware is involved.
"""
from collections.abc import Iterable

from farm.contracts.events import DeviceEvent, DeviceEventKind, DeviceEventSource
from farm.contracts.seats import DeviceMatch, DeviceRole, SeatSpec
from farm.testing.clock import FakeClock
from farm.testing.events import FakeDeviceEventSource

# Plausible udev identities. Four lowercase hex digits, as DeviceEvent requires.
_USB_IDS = {
    DeviceRole.HID_BOARD: ("303a", "1001"),  # ESP32-S3
    DeviceRole.CAPTURE_CARD: ("1d6b", "0002"),
    DeviceRole.PHONE: ("18d1", "4e40"),
}


class SimDevice:
    """One enrolled seat whose devices can appear and disappear from the bus."""

    def __init__(
        self,
        spec: SeatSpec,
        clock: FakeClock | None = None,
        present: Iterable[DeviceRole] | None = None,
    ) -> None:
        """`present` lists roles already attached at construction, for the
        host-restart (coldplug) scenario."""
        self.spec = spec
        self._clock = clock or FakeClock()
        self._source = FakeDeviceEventSource()
        self._attached: dict[DeviceRole, DeviceEvent] = {}
        if present is not None:
            self.attach(present)

    @property
    def source(self) -> DeviceEventSource:
        return self._source

    def attach(self, roles: Iterable[DeviceRole] | None = None) -> tuple[DeviceEvent, ...]:
        """Attach every required device, or just the named subset."""
        selected = list(roles) if roles is not None else list(self.spec.devices)
        events: list[DeviceEvent] = []
        for role in selected:
            match = self.spec.devices[role]  # KeyError for an unenrolled role
            if role in self._attached:
                raise ValueError(f"{role.value} is already attached")
            event = self._make_event(DeviceEventKind.ATTACHED, role, match)
            self._attached[role] = event
            self._source.push(event)
            events.append(event)
        return tuple(events)

    def detach(self) -> tuple[DeviceEvent, ...]:
        """Detach whatever is currently attached; identity fields are preserved."""
        events: list[DeviceEvent] = []
        for role, attached in reversed(list(self._attached.items())):
            event = attached.model_copy(
                update={
                    "kind": DeviceEventKind.DETACHED,
                    "observed_ns": self._tick(),
                }
            )
            self._source.push(event)
            events.append(event)
        self._attached.clear()
        return tuple(events)

    def close(self) -> None:
        self._source.close()

    def _make_event(
        self, kind: DeviceEventKind, role: DeviceRole, match: DeviceMatch
    ) -> DeviceEvent:
        vendor_id, product_id = _USB_IDS[role]
        suffix = f"{self.spec.seat_id}-{role.value}"
        return DeviceEvent(
            kind=kind,
            by_id=match.by_id or f"sim-{suffix}",
            by_path=match.by_path,
            vendor_id=vendor_id,
            product_id=product_id,
            serial=f"sim-{suffix}",
            observed_ns=self._tick(),
        )

    def _tick(self) -> int:
        self._clock.advance_ms(1)
        return self._clock.now_ns()
