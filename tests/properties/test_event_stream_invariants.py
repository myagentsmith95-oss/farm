"""Stream discipline: seq is gapless from 1 and ts_ns never decreases."""
from hypothesis import given, strategies as st

from farm.contracts.event_log import Event
from farm.testing.invariants import check_stream


def stream(pairs):
    return [Event(seq=s, ts_ns=t, kind="tick") for s, t in pairs]


def test_empty_stream_is_valid():
    assert check_stream([]) == []


def test_well_formed_stream_is_valid():
    assert check_stream(stream([(1, 10), (2, 20), (3, 30)])) == []


def test_equal_timestamps_are_allowed():
    assert check_stream(stream([(1, 10), (2, 10), (3, 10)])) == []


def test_seq_gap_is_reported():
    assert check_stream(stream([(1, 10), (2, 20), (4, 30)])) != []


def test_duplicate_seq_is_reported():
    assert check_stream(stream([(1, 10), (2, 20), (2, 30)])) != []


def test_stream_not_starting_at_first_seq_is_reported():
    assert check_stream(stream([(2, 10), (3, 20)])) != []


def test_first_seq_can_be_overridden_for_a_tail():
    assert check_stream(stream([(5, 10), (6, 20)]), first_seq=5) == []


def test_decreasing_timestamp_is_reported():
    assert check_stream(stream([(1, 20), (2, 10)])) != []


deltas = st.lists(st.integers(min_value=0, max_value=1000), min_size=1, max_size=30)


def build(steps):
    pairs, ts = [], 0
    for index, step in enumerate(steps):
        ts += step
        pairs.append((index + 1, ts))
    return stream(pairs)


@given(deltas)
def test_generated_valid_streams_pass(steps):
    assert check_stream(build(steps)) == []


@given(st.lists(st.integers(min_value=0, max_value=1000), min_size=2, max_size=30), st.data())
def test_swapping_adjacent_events_is_always_caught(steps, data):
    events = build(steps)
    i = data.draw(st.integers(min_value=0, max_value=len(events) - 2))
    events[i], events[i + 1] = events[i + 1], events[i]
    assert check_stream(events) != []
