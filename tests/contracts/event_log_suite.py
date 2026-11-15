"""Reusable contract suite for EventLog implementations.

Subclass EventLogContract in a class whose name starts with Test and implement
make_rig(). An implementation must read time from the injected clock. Rules:
- seq starts at 1 and increases by exactly 1 (gapless)
- ts_ns comes from the clock and never decreases, even if the clock does
- an invalid event raises ValueError and consumes no sequence number
- since(n) returns the events with seq > n, in order, as a new list
- since() with a negative number raises ValueError
"""
from dataclasses import dataclass

import pytest

from farm.contracts.event_log import Event, EventLog
from farm.testing.clock import FakeClock


@dataclass
class EventLogRig:
    log: EventLog
    clock: FakeClock


class EventLogContract:
    def make_rig(self) -> EventLogRig:
        raise NotImplementedError

    @pytest.fixture
    def rig(self):
        return self.make_rig()

    def test_satisfies_protocol(self, rig):
        assert isinstance(rig.log, EventLog)

    def test_first_event_has_seq_one(self, rig):
        assert rig.log.append("lease.acquired").seq == 1

    def test_seq_is_gapless_and_increasing(self, rig):
        seqs = [rig.log.append("tick").seq for _ in range(5)]
        assert seqs == [1, 2, 3, 4, 5]

    def test_ts_comes_from_the_clock(self, rig):
        first = rig.log.append("tick")
        assert first.ts_ns == rig.clock.now_ns()
        rig.clock.advance_ms(5)
        second = rig.log.append("tick")
        assert second.ts_ns == rig.clock.now_ns()

    def test_ts_never_goes_backwards_when_the_clock_does(self, rig):
        first = rig.log.append("tick")
        rig.clock.advance_ms(-10)
        second = rig.log.append("tick")
        assert second.ts_ns >= first.ts_ns

    def test_event_carries_kind_device_and_data(self, rig):
        event = rig.log.append("action.performed", device_id="seat-01", data={"x": 1})
        assert isinstance(event, Event)
        assert (event.kind, event.device_id, event.data) == (
            "action.performed",
            "seat-01",
            {"x": 1},
        )

    def test_optional_fields_default(self, rig):
        event = rig.log.append("tick")
        assert event.device_id is None
        assert event.data == {}

    def test_failed_append_consumes_no_seq(self, rig):
        with pytest.raises(ValueError):
            rig.log.append("Not A Kind")
        assert rig.log.append("tick").seq == 1

    def test_invalid_kind_raises_value_error(self, rig):
        with pytest.raises(ValueError):
            rig.log.append("")

    def test_since_zero_returns_everything_in_order(self, rig):
        written = [rig.log.append("tick") for _ in range(3)]
        assert rig.log.since(0) == written

    def test_since_returns_only_newer_events(self, rig):
        written = [rig.log.append("tick") for _ in range(4)]
        assert rig.log.since(2) == written[2:]

    def test_since_last_is_empty(self, rig):
        rig.log.append("tick")
        rig.log.append("tick")
        assert rig.log.since(2) == []
        assert rig.log.since(99) == []

    def test_since_negative_raises(self, rig):
        with pytest.raises(ValueError):
            rig.log.since(-1)

    def test_since_returns_a_copy(self, rig):
        rig.log.append("tick")
        rig.log.append("tick")
        got = rig.log.since(0)
        got.clear()
        assert len(rig.log.since(0)) == 2
