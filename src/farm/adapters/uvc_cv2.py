"""UVC capture adapter: MJPG 1080p, no-signal detection, active-area crop.

Hardware facts are from docs/ARCHITECTURE.md §7. The image helpers are pure so
they can be tested with synthetic frames; `refresh()` is the explicit grab step
and `latest()` only judges freshness of the stored frame (never waits).
"""
from __future__ import annotations

import time
from typing import Any

import cv2
import numpy as np

from farm.contracts.errors import CaptureError, StaleFrame
from farm.contracts.frame import Frame, FrameSource

_WIDTH = 1920
_HEIGHT = 1080
_SETTLE_S = 2.0
_WARMUP = 15


def is_color_bars(frame: Any) -> bool:
    """True for the capture card's no-signal test pattern."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    if float(np.mean(sat > 150)) < 0.35:
        return False
    small = cv2.resize(frame, (64, 36)).astype(np.float32)
    return float(small.var(axis=0).mean()) < 500


def find_active_area(frame: Any) -> tuple[int, int, int, int] | None:
    """Inclusive (x0, y0, x1, y1) of the portrait phone inside the pillarboxes."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    corners = [
        gray[:40, :40],
        gray[:40, -40:],
        gray[-40:, :40],
        gray[-40:, -40:],
    ]
    background = min(int(np.median(corner)) for corner in corners)
    threshold = background + 25
    columns = np.where(gray.mean(axis=0) > threshold)[0]
    if len(columns) == 0 or len(columns) > 0.6 * width:
        return None
    x0, x1 = int(columns[0]), int(columns[-1])
    rows = np.where(gray[:, x0 : x1 + 1].mean(axis=1) > threshold)[0]
    if len(rows) == 0:
        return None
    return (x0, int(rows[0]), x1, int(rows[-1]))


class UvcCaptureSource:
    """One capture card. The runner drives `refresh()`; `latest()` never blocks."""

    source = FrameSource.UVC

    def __init__(
        self,
        video_dev: str,
        settle_s: float = _SETTLE_S,
        warmup: int = _WARMUP,
    ) -> None:
        self.video_dev = video_dev
        self._settle_s = settle_s
        self._warmup = warmup
        self._cap: Any = None
        self._latest: Frame | None = None
        self._started = False
        self._closed = False
        self.area: tuple[int, int, int, int] | None = None

    def start(self) -> None:
        if self._closed:
            raise CaptureError("source is closed")
        self._cap = cv2.VideoCapture(self.video_dev, cv2.CAP_V4L2)
        if not self._cap.isOpened():
            raise CaptureError(f"cannot open {self.video_dev}")
        self._cap.set(
            cv2.CAP_PROP_FOURCC,
            cv2.VideoWriter_fourcc(*"MJPG"),  # type: ignore[attr-defined]
        )
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, _WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, _HEIGHT)
        time.sleep(self._settle_s)
        for _ in range(self._warmup):
            self._cap.read()
        self._started = True

    def refresh(self) -> Frame:
        """Grab one frame, crop to the active area and store it as the latest."""
        if self._closed or not self._started:
            raise CaptureError("source is not running")
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise CaptureError("capture read failed")
        if is_color_bars(frame):
            raise StaleFrame("no HDMI signal")
        area = find_active_area(frame)
        if area is None:
            raise StaleFrame("no active area")
        x0, y0, x1, y1 = area
        self.area = area
        crop = frame[y0 : y1 + 1, x0 : x1 + 1]
        encoded, data = cv2.imencode(".jpg", crop)
        if not encoded:
            raise CaptureError("frame encode failed")
        self._latest = Frame(
            width=x1 - x0 + 1,
            height=y1 - y0 + 1,
            captured_ns=time.monotonic_ns(),
            source=FrameSource.UVC,
            data=data.tobytes(),
        )
        return self._latest

    def latest(self, max_age_ms: int) -> Frame:
        if max_age_ms < 0:
            raise ValueError(f"max_age_ms must not be negative, got {max_age_ms}")
        if self._closed or not self._started:
            raise CaptureError("source is not running")
        if self._latest is None:
            raise StaleFrame("no frame captured yet")
        age_ns = time.monotonic_ns() - self._latest.captured_ns
        if age_ns > max_age_ms * 1_000_000:
            raise StaleFrame(f"newest frame is {age_ns // 1_000_000} ms old")
        return self._latest

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._started = False
            if self._cap is not None:
                self._cap.release()
                self._cap = None
