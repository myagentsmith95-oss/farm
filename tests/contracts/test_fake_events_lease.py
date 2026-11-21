from events_suite import EventRig, EventSourceContract
from lease_suite import LeaseManagerContract, LeaseRig

from farm.testing.clock import FakeClock
from farm.testing.events import FakeDeviceEventSource
from farm.testing.lease import FakeLeaseManager


class TestFakeDeviceEventSource(EventSourceContract):
    def make_rig(self):
        source = FakeDeviceEventSource()
        return EventRig(source=source, feed=source.push, preload=source.push)


class TestFakeLeaseManager(LeaseManagerContract):
    def make_rig(self):
        clock = FakeClock()
        return LeaseRig(manager=FakeLeaseManager(clock_ns=clock.now_ns), clock=clock)


def test_fake_source_returns_without_blocking_when_empty():
    # The fake is finite so CI never hangs; a real adapter blocks while open.
    assert list(FakeDeviceEventSource().events()) == []


def test_fake_lease_tokens_are_counted_per_device():
    clock = FakeClock()
    manager = FakeLeaseManager(clock_ns=clock.now_ns)
    first = manager.acquire("seat-01", "runner-a", 1000)
    other = manager.acquire("seat-02", "runner-a", 1000)
    assert first.token == other.token == 1
