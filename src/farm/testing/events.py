"""In-memory DeviceEventSource. Tests push events; the feed is finite so CI never hangs."""
from collections import deque
from collections.abc import Iterator

from farm.contracts.events import DeviceEvent


class FakeDeviceEventSource:
    def __init__(self) -> None:
        self._queue: deque[DeviceEvent] = deque()
        self.closed = False

    def push(self, event: DeviceEvent) -> None:
        self._queue.append(event)

    def events(self) -> Iterator[DeviceEvent]:
        while self._queue:
            yield self._queue.popleft()

    def close(self) -> None:
        self.closed = True
