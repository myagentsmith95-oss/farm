"""Invariant checks for event streams, used by tests."""
from collections.abc import Sequence

from farm.contracts.event_log import Event


def check_stream(events: Sequence[Event], *, first_seq: int = 1) -> list[str]:
    """Return a description of every violation: seq must run first_seq,
    first_seq + 1, ... with no gaps or repeats, and ts_ns must never decrease."""
    problems: list[str] = []
    previous: Event | None = None
    for index, event in enumerate(events):
        expected = first_seq + index
        if event.seq != expected:
            problems.append(f"position {index}: expected seq {expected}, got {event.seq}")
        if previous is not None and event.ts_ns < previous.ts_ns:
            problems.append(
                f"position {index}: ts_ns {event.ts_ns} is before {previous.ts_ns}"
            )
        previous = event
    return problems
