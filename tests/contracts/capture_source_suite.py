"""Reusable contract suite for CaptureSource implementations.

Subclass CaptureSourceContract in a class whose name starts with Test, and
implement make_rig(). An adapter must read time from the injected clock so
freshness is testable. Rules:
- latest() before start() or after close() raises CaptureError
- no frame yet, or a frame older than max_age_ms, raises StaleFrame
- a frame is fresh while its age is <= max_age_ms (boundary included)
- latest() returns the newest frame; close() is idempotent
"""
from collections.abc import Callable
from dataclasses import dataclass

import pytest

from farm.contracts.capture import CaptureSource
from farm.contracts.errors import CaptureError, StaleFrame
from farm.contracts.frame import Frame, FrameSource
from farm.testing.clock import FakeClock


@dataclass
class Rig:
    source: CaptureSource
    clock: FakeClock
    feed: Callable[[Frame], None]


def frame_at(kind: FrameSource, captured_ns: int) -> Frame:
    return Frame(
        width=1080,
        height=2400,
        captured_ns=captured_ns,
        source=kind,
        data=b"\xff\xd8x\xff\xd9",
    )


class CaptureSourceContract:
    def make_rig(self) -> Rig:
        raise NotImplementedError

    @pytest.fixture
    def rig(self):
        instance = self.make_rig()
        yield instance
        instance.source.close()

    def test_satisfies_protocol(self, rig):
        assert isinstance(rig.source, CaptureSource)
        assert isinstance(rig.source.source, FrameSource)

    def test_latest_before_start_raises_capture_error(self, rig):
        with pytest.raises(CaptureError):
            rig.source.latest(100)

    def test_started_without_frames_is_stale(self, rig):
        rig.source.start()
        with pytest.raises(StaleFrame):
            rig.source.latest(100)

    def test_fresh_frame_is_returned(self, rig):
        rig.source.start()
        frame = frame_at(rig.source.source, rig.clock.now_ns())
        rig.feed(frame)
        assert rig.source.latest(100) == frame

    def test_frame_exactly_at_max_age_is_fresh(self, rig):
        rig.source.start()
        frame = frame_at(rig.source.source, rig.clock.now_ns())
        rig.feed(frame)
        rig.clock.advance_ms(100)
        assert rig.source.latest(100) == frame

    def test_frame_older_than_max_age_is_stale(self, rig):
        rig.source.start()
        rig.feed(frame_at(rig.source.source, rig.clock.now_ns()))
        rig.clock.advance_ms(101)
        with pytest.raises(StaleFrame):
            rig.source.latest(100)

    def test_latest_returns_the_newest_frame(self, rig):
        rig.source.start()
        rig.feed(frame_at(rig.source.source, rig.clock.now_ns()))
        rig.clock.advance_ms(10)
        newest = frame_at(rig.source.source, rig.clock.now_ns())
        rig.feed(newest)
        assert rig.source.latest(1000) == newest

    def test_latest_after_close_raises_capture_error(self, rig):
        rig.source.start()
        rig.feed(frame_at(rig.source.source, rig.clock.now_ns()))
        rig.source.close()
        with pytest.raises(CaptureError):
            rig.source.latest(1000)

    def test_close_is_idempotent(self, rig):
        rig.source.start()
        rig.source.close()
        rig.source.close()
