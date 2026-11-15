"""Action invariants: coordinates are normalized (0 to 1), kinds are tagged."""
import pytest
from hypothesis import given, strategies as st
from pydantic import TypeAdapter, ValidationError

from farm.contracts.actions import Action, Key, Swipe, Tap, Text

inside = st.floats(min_value=0.0, max_value=1.0)
outside = st.one_of(
    st.floats(max_value=-1e-9, allow_nan=False),
    st.floats(min_value=1.0 + 1e-9, allow_nan=False),
)
adapter = TypeAdapter(Action)


@given(inside, inside)
def test_tap_accepts_normalized_coordinates(x, y):
    tap = Tap(x=x, y=y)
    assert (tap.x, tap.y) == (x, y)


@given(outside)
def test_tap_rejects_out_of_range_x(bad):
    with pytest.raises(ValidationError):
        Tap(x=bad, y=0.5)


@given(outside)
def test_tap_rejects_out_of_range_y(bad):
    with pytest.raises(ValidationError):
        Tap(x=0.5, y=bad)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_tap_rejects_nan_and_infinity(bad):
    with pytest.raises(ValidationError):
        Tap(x=bad, y=0.5)


@given(inside, inside, inside, inside)
def test_swipe_accepts_normalized_coordinates(x1, y1, x2, y2):
    swipe = Swipe(x1=x1, y1=y1, x2=x2, y2=y2, duration_ms=300)
    assert (swipe.x1, swipe.y1, swipe.x2, swipe.y2) == (x1, y1, x2, y2)


@given(outside)
def test_swipe_rejects_out_of_range_end_point(bad):
    with pytest.raises(ValidationError):
        Swipe(x1=0.1, y1=0.1, x2=bad, y2=0.5, duration_ms=300)


@pytest.mark.parametrize("duration", [0, -1])
def test_swipe_rejects_non_positive_duration(duration):
    with pytest.raises(ValidationError):
        Swipe(x1=0.1, y1=0.1, x2=0.9, y2=0.9, duration_ms=duration)


@pytest.mark.parametrize("code", ["", "   "])
def test_key_rejects_blank_code(code):
    with pytest.raises(ValidationError):
        Key(code=code)


def test_text_rejects_empty_value():
    with pytest.raises(ValidationError):
        Text(value="")


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        Tap(x=0.5, y=0.5, pressure=1.0)


def test_actions_are_immutable():
    tap = Tap(x=0.5, y=0.5)
    with pytest.raises(ValidationError):
        tap.x = 0.1


@pytest.mark.parametrize(
    "action",
    [
        Tap(x=0.25, y=0.75),
        Swipe(x1=0.1, y1=0.2, x2=0.8, y2=0.9, duration_ms=250),
        Key(code="HOME"),
        Text(value="hello"),
    ],
)
def test_union_round_trips_through_plain_dicts(action):
    assert adapter.validate_python(action.model_dump()) == action


def test_union_picks_the_class_from_kind():
    parsed = adapter.validate_python({"kind": "tap", "x": 0.5, "y": 0.5})
    assert isinstance(parsed, Tap)


def test_union_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "pinch", "x": 0.5, "y": 0.5})


def test_kind_cannot_be_overridden_to_another_kind():
    with pytest.raises(ValidationError):
        Tap(kind="swipe", x=0.5, y=0.5)
