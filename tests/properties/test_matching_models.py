"""Region, Match and TextHit: normalized (0 to 1) results from vision."""
import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from farm.contracts.matching import Match, Region, TextHit

unit = st.floats(min_value=0.0, max_value=1.0)


@st.composite
def region_args(draw):
    x = draw(st.floats(min_value=0.0, max_value=0.99))
    y = draw(st.floats(min_value=0.0, max_value=0.99))
    width = draw(st.floats(min_value=0.001, max_value=1.0 - x))
    height = draw(st.floats(min_value=0.001, max_value=1.0 - y))
    return dict(x=x, y=y, width=width, height=height)


BOX = Region(x=0.2, y=0.2, width=0.4, height=0.4)


@given(region_args())
def test_region_accepts_valid_geometry(args):
    region = Region(**args)
    assert (region.x, region.width) == (args["x"], args["width"])


@pytest.mark.parametrize("field", ["width", "height"])
@pytest.mark.parametrize("bad", [0.0, -0.1])
def test_region_rejects_non_positive_size(field, bad):
    args = dict(x=0.1, y=0.1, width=0.2, height=0.2)
    args[field] = bad
    with pytest.raises(ValidationError):
        Region(**args)


@pytest.mark.parametrize(
    "args",
    [
        dict(x=0.5, y=0.0, width=0.6, height=0.5),
        dict(x=0.0, y=0.5, width=0.5, height=0.6),
    ],
)
def test_region_rejects_overflow_past_the_screen_edge(args):
    with pytest.raises(ValidationError):
        Region(**args)


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_region_rejects_out_of_range_origin(bad):
    with pytest.raises(ValidationError):
        Region(x=bad, y=0.0, width=0.1, height=0.1)


def test_region_rejects_nan():
    with pytest.raises(ValidationError):
        Region(x=float("nan"), y=0.0, width=0.1, height=0.1)


@given(region_args())
def test_region_contains_itself(args):
    region = Region(**args)
    assert region.contains(region)


def test_region_contains_smaller_region():
    inner = Region(x=0.3, y=0.3, width=0.1, height=0.1)
    assert BOX.contains(inner)


def test_region_does_not_contain_overhanging_region():
    overhang = Region(x=0.5, y=0.5, width=0.3, height=0.3)
    assert not BOX.contains(overhang)


@given(region_args())
def test_region_center_stays_on_screen(args):
    cx, cy = Region(**args).center
    assert 0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0


@given(unit)
def test_match_accepts_unit_score(score):
    assert Match(region=BOX, score=score).score == score


@pytest.mark.parametrize("bad", [-0.1, 1.1, float("nan")])
def test_match_rejects_bad_score(bad):
    with pytest.raises(ValidationError):
        Match(region=BOX, score=bad)


def test_match_center_is_region_center():
    assert Match(region=BOX, score=0.9).center == BOX.center


@pytest.mark.parametrize("text", ["", "   "])
def test_text_hit_rejects_blank_text(text):
    with pytest.raises(ValidationError):
        TextHit(text=text, region=BOX, confidence=0.9)


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_text_hit_rejects_bad_confidence(bad):
    with pytest.raises(ValidationError):
        TextHit(text="ok", region=BOX, confidence=bad)


def test_models_are_immutable():
    with pytest.raises(ValidationError):
        BOX.x = 0.5


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        Region(x=0.1, y=0.1, width=0.2, height=0.2, angle=5)
