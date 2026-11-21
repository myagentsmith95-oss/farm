"""In-memory DeviceEventSource. Tests push events; the feed is finite so CI never hangs.

Coldplug is modelled as a separate preload list so the contract suite can
catch an adapter that ignores already-present devices. close() seals the
feed: events buffered before close are still delivered, but later push() or
preload() calls are dropped. The seal is a fake determinism choice; a real
udev Monitor manages its own lifetime and may behave differently.
"""
from collections import deque
from collections.abc import Iterable, Iterator

from farm.contracts.events import DeviceEvent


class FakeDeviceEventSource:
    def __init__(self, present: Iterable[DeviceEvent] = ()) -> None:
        self._preload: list[DeviceEvent] = list(present)
        self._queue: deque[DeviceEvent] = deque()
        self.closed = False

    def preload(self, event: DeviceEvent) -> None:
        """Register an already-present device; ignored after close()."""
        if not self.closed:
            self._preload.append(event)

    def push(self, event: DeviceEvent) -> None:
        if not self.closed:
            self._queue.append(event)

    def events(self) -> Iterator[DeviceEvent]:
        # One iteration per source: preloaded devices first, in order.
        yield from self._preload
        while self._queue:
            yield self._queue.popleft()

    def close(self) -> None:
        self.closed = True
