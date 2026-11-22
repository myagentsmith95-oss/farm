"""Capture image helpers, tested with synthetic frames — no camera needed."""
import cv2
import numpy as np

from farm.adapters.uvc_cv2 import (
    UvcCaptureSource,
    find_active_area,
    is_color_bars,
    stable_area,
)


def color_bar_frame():
    hsv = np.zeros((1080, 1920, 3), dtype=np.uint8)
    hsv[:, :, 0] = 90
    hsv[:, :, 1] = 255
    hsv[:, :, 2] = 255
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def phone_frame():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[0:1019, 713:1207] = 200
    return frame


def test_finds_portrait_phone_inside_pillarboxes():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[0:1019, 713:1207] = 200
    assert find_active_area(frame) == (713, 0, 1206, 1018)


def test_dim_screen_is_detected_by_coverage_not_mean():
    # Dim content (luma 30 covering 80% of the phone rect) has a column mean
    # of 24, below the old bg+25 threshold, but clearly covers the area.
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[0:1019, 713:1207, :] = 30
    assert find_active_area(frame) == (713, 0, 1206, 1018)


def test_no_signal_returns_none():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert find_active_area(frame) is None


def test_wide_test_pattern_is_rejected():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[:, :] = 200
    assert find_active_area(frame) is None


def test_solid_high_saturation_is_no_signal():
    hsv = np.zeros((36, 64, 3), dtype=np.uint8)
    hsv[:, :, 0] = 90
    hsv[:, :, 1] = 255
    hsv[:, :, 2] = 255
    frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    assert is_color_bars(frame) is True


def test_neutral_photo_is_not_no_signal():
    frame = np.full((36, 64, 3), 128, dtype=np.uint8)
    frame[10:20, 10:30] = 40
    assert is_color_bars(frame) is False


def test_stable_area_picks_the_dominant_cluster():
    jittery = [
        (713, 10, 1205, 1059),
        (746, 17, 1202, 1060),
        (715, 12, 1204, 1058),
        (743, 15, 1203, 1061),
        (714, 11, 1205, 1060),
    ]
    area = stable_area(jittery)
    assert area is not None
    assert 713 <= area[0] <= 715
    assert 1204 <= area[2] <= 1205


def test_stable_area_needs_enough_good_samples():
    assert stable_area([(713, 10, 1205, 1059), None]) is None


def test_refresh_waits_for_hdmi_lock_after_color_bars():
    class FakeCap:
        def __init__(self, frames):
            self.frames = frames
            self.index = 0

        def read(self):
            frame = self.frames[min(self.index, len(self.frames) - 1)]
            self.index += 1
            return True, frame

    source = UvcCaptureSource(
        "/dev/fake", signal_timeout_s=0.2, retry_interval_s=0.01
    )
    source._cap = FakeCap([color_bar_frame(), color_bar_frame(), phone_frame()])
    source._started = True
    frame = source.refresh()
    assert frame.width == 494 and frame.height == 1019
    assert source.area == (713, 0, 1206, 1018)


def test_refresh_times_out_when_signal_never_appears():
    class FakeCap:
        def read(self):
            return True, color_bar_frame()

    source = UvcCaptureSource(
        "/dev/fake", signal_timeout_s=0.05, retry_interval_s=0.01
    )
    source._cap = FakeCap()
    source._started = True
    try:
        source.refresh()
        assert False, "expected StaleFrame"
    except Exception as exc:
        assert type(exc).__name__ == "StaleFrame"
