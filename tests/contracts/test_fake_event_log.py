from event_log_suite import EventLogContract, EventLogRig
from hypothesis import given, strategies as st

from farm.testing.clock import FakeClock
from farm.testing.event_log import FakeEventLog
from farm.testing.invariants import check_stream


class TestFakeEventLog(EventLogContract):
    def make_rig(self):
        clock = FakeClock()
        return EventLogRig(log=FakeEventLog(clock_ns=clock.now_ns), clock=clock)


@given(st.lists(st.integers(min_value=-50, max_value=50), max_size=40))
def test_fake_log_streams_always_pass_the_stream_check(steps):
    clock = FakeClock()
    log = FakeEventLog(clock_ns=clock.now_ns)
    for step in steps:
        clock.advance_ms(step)
        log.append("tick")
    assert check_stream(log.since(0)) == []


def test_default_clock_is_monotonic():
    log = FakeEventLog()
    first = log.append("tick")
    second = log.append("tick")
    assert second.ts_ns >= first.ts_ns
