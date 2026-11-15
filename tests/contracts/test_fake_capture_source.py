import pytest
from capture_source_suite import CaptureSourceContract, Rig

from farm.contracts.errors import CaptureError
from farm.contracts.frame import FrameSource
from farm.testing.capture import FakeCaptureSource
from farm.testing.clock import FakeClock


def build_rig(kind: FrameSource) -> Rig:
    clock = FakeClock()
    source = FakeCaptureSource(source=kind, clock_ns=clock.now_ns)
    return Rig(source=source, clock=clock, feed=source.push)


class TestFakeCaptureSourceUvc(CaptureSourceContract):
    def make_rig(self):
        return build_rig(FrameSource.UVC)


class TestFakeCaptureSourceAdbScreencap(CaptureSourceContract):
    def make_rig(self):
        return build_rig(FrameSource.ADB_SCREENCAP)


def test_start_after_close_raises_capture_error():
    source = FakeCaptureSource()
    source.close()
    with pytest.raises(CaptureError):
        source.start()
