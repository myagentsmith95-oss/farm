"""In-memory CaptureSource. Tests push frames; freshness uses an injected clock."""
import time
from collections.abc import Callable

from farm.contracts.errors import CaptureError, StaleFrame
from farm.contracts.frame import Frame, FrameSource


class FakeCaptureSource:
    def __init__(
        self,
        source: FrameSource = FrameSource.UVC,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self.source = source
        self._clock_ns = clock_ns
        self._started = False
        self._closed = False
        self._latest: Frame | None = None

    def push(self, frame: Frame) -> None:
        self._latest = frame

    def start(self) -> None:
        if self._closed:
            raise CaptureError("source is closed")
        self._started = True

    def latest(self, max_age_ms: int) -> Frame:
        if self._closed or not self._started:
            raise CaptureError("source is not running")
        if self._latest is None:
            raise StaleFrame("no frame captured yet")
        age_ns = self._clock_ns() - self._latest.captured_ns
        if age_ns > max_age_ms * 1_000_000:
            raise StaleFrame(f"newest frame is {age_ns // 1_000_000} ms old")
        return self._latest

    def close(self) -> None:
        self._closed = True
