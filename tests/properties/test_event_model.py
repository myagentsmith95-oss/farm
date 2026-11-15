"""Event log model: seq and ts_ns, a dotted kind, optional device, JSON data."""
import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from farm.contracts.event_log import Event


def make(**overrides):
    fields = dict(seq=1, ts_ns=0, kind="action.performed")
    fields.update(overrides)
    return Event(**fields)


@given(st.integers(min_value=1, max_value=2**62), st.integers(min_value=0, max_value=2**62))
def test_event_accepts_valid_fields(seq, ts_ns):
    event = make(seq=seq, ts_ns=ts_ns)
    assert (event.seq, event.ts_ns) == (seq, ts_ns)


def test_event_optional_device_id_and_default_data():
    event = make()
    assert event.device_id is None
    assert event.data == {}


@pytest.mark.parametrize("kind", ["tap.performed", "lease", "a1.b_2.c"])
def test_event_accepts_valid_kinds(kind):
    assert make(kind=kind).kind == kind


@pytest.mark.parametrize(
    "kind", ["", "Tap", "tap.", ".tap", "tap..x", "1tap", "tap performed"]
)
def test_event_rejects_bad_kinds(kind):
    with pytest.raises(ValidationError):
        make(kind=kind)


@pytest.mark.parametrize("bad", [0, -1])
def test_event_rejects_non_positive_seq(bad):
    with pytest.raises(ValidationError):
        make(seq=bad)


def test_event_rejects_negative_timestamp():
    with pytest.raises(ValidationError):
        make(ts_ns=-1)


def test_event_rejects_blank_device_id():
    with pytest.raises(ValidationError):
        make(device_id="  ")


def test_event_accepts_nested_json_data():
    data = {"a": [1, 2.5, "x", None, True, {"b": []}]}
    assert make(data=data).data == data


def test_event_rejects_non_json_data():
    with pytest.raises(ValidationError):
        make(data={"x": object()})


def test_event_rejects_extra_fields():
    with pytest.raises(ValidationError):
        make(level="info")


def test_event_is_immutable():
    event = make()
    with pytest.raises(ValidationError):
        event.seq = 2


def test_event_round_trips_through_json():
    event = make(device_id="seat-01", data={"x": 1})
    assert Event.model_validate_json(event.model_dump_json()) == event
