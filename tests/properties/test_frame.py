"""Frame invariants: metadata is validated, pixels are not interpreted."""
import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from farm.contracts.frame import Frame, FrameSource

PIXELS = b"\xff\xd8fake-jpeg\xff\xd9"


def make(**overrides):
    fields = dict(
        width=1080,
        height=2400,
        captured_ns=123,
        source=FrameSource.UVC,
        data=PIXELS,
    )
    fields.update(overrides)
    return Frame(**fields)


@given(
    st.integers(min_value=1, max_value=10_000),
    st.integers(min_value=1, max_value=10_000),
    st.integers(min_value=0, max_value=2**62),
    st.sampled_from(FrameSource),
)
def test_accepts_valid_metadata(width, height, captured_ns, source):
    frame = make(width=width, height=height, captured_ns=captured_ns, source=source)
    assert (frame.width, frame.height) == (width, height)
    assert frame.captured_ns == captured_ns
    assert frame.source is source


@pytest.mark.parametrize("field", ["width", "height"])
@pytest.mark.parametrize("bad", [0, -1])
def test_rejects_non_positive_dimensions(field, bad):
    with pytest.raises(ValidationError):
        make(**{field: bad})


def test_rejects_negative_timestamp():
    with pytest.raises(ValidationError):
        make(captured_ns=-1)


def test_rejects_empty_payload():
    with pytest.raises(ValidationError):
        make(data=b"")


def test_rejects_unknown_source():
    with pytest.raises(ValidationError):
        make(source="webcam")


def test_accepts_source_names_as_strings():
    assert make(source="adb_screencap").source is FrameSource.ADB_SCREENCAP


def test_rejects_extra_fields():
    with pytest.raises(ValidationError):
        make(exposure=1)


def test_frame_is_immutable():
    frame = make()
    with pytest.raises(ValidationError):
        frame.width = 1
