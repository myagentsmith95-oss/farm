"""CaptureSource seam. PROVISIONAL: revisit after the W3 capture loop.

latest() never waits: it returns the newest frame or raises, and the runner
decides whether to retry. A frame is fresh while its age is <= max_age_ms,
measured against the monotonic clock that stamped Frame.captured_ns.
"""
from typing import Protocol, runtime_checkable

from farm.contracts.frame import Frame, FrameSource


@runtime_checkable
class CaptureSource(Protocol):
    source: FrameSource

    def start(self) -> None:
        """Begin capturing. Raises CaptureError if closed or the device fails."""
        ...

    def latest(self, max_age_ms: int) -> Frame:
        """Newest frame. Raises CaptureError if not started or closed,
        StaleFrame if there is no frame or it is older than max_age_ms, and
        ValueError if max_age_ms is negative. Zero accepts a frame stamped at
        the current clock."""
        ...

    def close(self) -> None:
        """Release the source. Safe to call more than once."""
        ...
