"""Reusable contract suite for DeviceEventSource implementations.

Subclass EventSourceContract in a class whose name starts with Test and
implement make_rig(). Rules: events fed before close() are delivered in order,
then iteration ends; iteration ends after close() when nothing was fed;
close() is idempotent. A real udev adapter blocks while the source is open and
must still drain buffered events before ending.
"""
from collections.abc import Callable
from dataclasses import dataclass

import pytest

from farm.contracts.events import DeviceEvent, DeviceEventKind, DeviceEventSource


def make_event(by_id, kind=DeviceEventKind.ATTACHED, observed_ns=1):
    return DeviceEvent(
        kind=kind,
        by_id=by_id,
        vendor_id="303a",
        product_id="1001",
        observed_ns=observed_ns,
    )


@dataclass
class EventRig:
    source: DeviceEventSource
    feed: Callable[[DeviceEvent], None]


class EventSourceContract:
    def make_rig(self) -> EventRig:
        raise NotImplementedError

    @pytest.fixture
    def rig(self):
        instance = self.make_rig()
        yield instance
        instance.source.close()

    def test_satisfies_protocol(self, rig):
        assert isinstance(rig.source, DeviceEventSource)

    def test_delivers_events_fed_before_close_in_order(self, rig):
        first = make_event("usb-a", DeviceEventKind.ATTACHED, 1)
        second = make_event("usb-a", DeviceEventKind.DETACHED, 2)
        rig.feed(first)
        rig.feed(second)
        rig.source.close()
        assert list(rig.source.events()) == [first, second]

    def test_iteration_ends_after_close_when_nothing_was_fed(self, rig):
        rig.source.close()
        assert list(rig.source.events()) == []

    def test_close_is_idempotent(self, rig):
        rig.source.close()
        rig.source.close()
