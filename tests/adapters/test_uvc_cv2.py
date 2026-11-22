"""Capture image helpers, tested with synthetic frames — no camera needed."""
import cv2
import numpy as np

from farm.adapters.uvc_cv2 import find_active_area, is_color_bars


def test_finds_portrait_phone_inside_pillarboxes():
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[0:1019, 713:1207] = 200
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
