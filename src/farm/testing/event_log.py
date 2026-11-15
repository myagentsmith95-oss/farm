"""In-memory EventLog with an injected clock."""
import time
from collections.abc import Callable, Mapping

from pydantic import JsonValue

from farm.contracts.event_log import Event


class FakeEventLog:
    def __init__(self, clock_ns: Callable[[], int] = time.monotonic_ns) -> None:
        self._clock_ns = clock_ns
        self._events: list[Event] = []
        self._last_ts = 0

    def append(
        self,
        kind: str,
        *,
        device_id: str | None = None,
        data: Mapping[str, JsonValue] | None = None,
    ) -> Event:
        ts_ns = max(self._clock_ns(), self._last_ts)
        event = Event(  # validates before anything is recorded
            seq=len(self._events) + 1,
            ts_ns=ts_ns,
            kind=kind,
            device_id=device_id,
            data=dict(data or {}),
        )
        self._events.append(event)
        self._last_ts = ts_ns
        return event

    def since(self, seq: int) -> list[Event]:
        if seq < 0:
            raise ValueError(f"seq must not be negative, got {seq}")
        return self._events[seq:]
