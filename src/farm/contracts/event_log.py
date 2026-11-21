"""Event log seam. PROVISIONAL: revisit when the supervisor is written (W7).

The supervisor is the single writer. seq is gapless from 1 and ts_ns never
decreases; consumers (dashboard, logger, API) only read. Not to be confused
with DeviceEvent, which is the udev attach/detach model.
"""
from collections.abc import Mapping
from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Kind = Annotated[
    str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
]


class Event(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seq: Annotated[int, Field(ge=1)]
    ts_ns: Annotated[int, Field(ge=0)]  # time.monotonic_ns() on the farm host
    kind: Kind  # lowercase dotted name, e.g. "action.performed"
    device_id: NonBlank | None = None
    data: dict[str, JsonValue] = Field(default_factory=dict)


@runtime_checkable
class EventLog(Protocol):
    def append(
        self,
        kind: str,
        *,
        device_id: str | None = None,
        data: Mapping[str, JsonValue] | None = None,
    ) -> Event:
        """Record an event, assigning the next seq and a non-decreasing ts_ns.
        Raises ValueError for an invalid event; nothing is recorded then."""
        ...

    def since(self, seq: int) -> list[Event]:
        """Events with seq greater than the given one, in order, as a new list.
        Raises ValueError if seq is negative. Results are deep copies: a
        consumer editing one cannot change the stored log."""
        ...
