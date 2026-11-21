"""DeviceEvent seam: attach and detach events from the udev layer.

PROVISIONAL: revisit when the pyudev adapter is written (W1 registry). Not to
be confused with the Event log model (seq and ts), which is a separate type.
A source's events() blocks while the source is open and ends after close();
events observed before close() are still delivered, in order. A source must
also enumerate already-present devices at iteration start (coldplug) — see
DeviceEventSource.events().
"""
from collections.abc import Iterator
from enum import StrEnum
from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
UsbId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{4}$")]


class DeviceEventKind(StrEnum):
    ATTACHED = "attached"
    DETACHED = "detached"


class DeviceEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: DeviceEventKind
    by_id: NonBlank  # stable name, e.g. /dev/serial/by-id/... entry
    by_path: NonBlank | None = None  # physical USB port path
    vendor_id: UsbId  # four lowercase hex digits
    product_id: UsbId
    serial: NonBlank | None = None
    observed_ns: Annotated[int, Field(ge=0)]  # time.monotonic_ns() on the host


@runtime_checkable
class DeviceEventSource(Protocol):
    def events(self) -> Iterator[DeviceEvent]:
        """Device events in the order observed.

        Coldplug: when iteration begins, yield a synthetic ATTACHED event for
        every already-present matching device, in a stable order, before any
        live change event. A host restart with all devices still plugged in
        must reach the same state as a fresh plug sequence.
        """
        ...

    def close(self) -> None:
        """Stop the source. Safe to call more than once."""
        ...
