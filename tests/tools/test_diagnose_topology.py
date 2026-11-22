"""Diagnostic helpers: classify failures, enforce topology, recover a hung board."""
from collections import deque

from tools.diagnose_topology import (
    check_hid_attach,
    classify_capture_problem,
    classify_tap,
    force_reset,
    missing_expected,
)


def test_capture_problem_classification():
    assert classify_capture_problem("CaptureError: cannot open /dev/video0") == "BUSY"
    assert classify_capture_problem("StaleFrame: no HDMI signal") == "NO_SIGNAL"
    assert classify_capture_problem("StaleFrame: no active area") == "BLACK"
    assert classify_capture_problem("CaptureError: capture read failed") == "ERROR"


class FakeSerial:
    def __init__(self, lines):
        self.lines = deque(lines)
        self.written = []
        self.rts = None
        self.dtr = None

    def write(self, data):
        self.written.append(data)

    def readline(self):
        return self.lines.popleft() if self.lines else b""


def test_force_reset_watches_for_boot_and_ready():
    serial = FakeSerial([b"BOOT touch-fw-2\n", b"READY\n"])
    boot, ready, pings, res_ok = force_reset(serial, wait_s=0.15)
    assert boot is True and ready is True and pings >= 1
    assert serial.written[0] == b"PING\n"
    assert serial.dtr is False and serial.rts is False
    assert res_ok is False


def test_force_reset_resends_res_when_resolution_known():
    serial = FakeSerial([b"BOOT touch-fw-2\n", b"READY\n", b"OK\n"])
    boot, ready, pings, res_ok = force_reset(
        serial, wait_s=0.2, resolution=(494, 1019)
    )
    assert boot and ready and res_ok
    assert b"RES 494 1019\n" in serial.written
    assert serial.written.index(b"RES 494 1019\n") > serial.written.index(b"PING\n")


def test_missing_expected_reports_vanished_devices():
    expected = {"esp32": ["board-a", "board-b"], "cards": ["card-a", "card-b"]}
    current = {"esp32": ["board-a"], "cards": ["card-a"]}
    assert missing_expected(expected, current) == ["board-b", "card-b"]


def test_missing_expected_is_empty_when_all_present():
    expected = {"esp32": ["board-a"], "cards": ["card-a"]}
    current = {"esp32": ["board-a", "board-b"], "cards": ["card-a"]}
    assert missing_expected(expected, current) == []


def test_classify_tap():
    assert classify_tap("DONE") == "DONE"
    assert classify_tap("ERR usb send failed") == "ERR"
    assert classify_tap("") == "OTHER"


def test_hid_attach_check_swipes_up_then_down():
    serial = FakeSerial([b"DONE\n", b"DONE\n"])
    assert check_hid_attach(serial, 494, 1019, wait_s=0.2) is True
    up, down = serial.written
    assert up.decode().startswith("SWIPE 247 ")
    assert down.decode().startswith("SWIPE 247 ")
    # up goes from the lower part of the screen to the upper part; down reverses
    y_up1, y_up2 = int(up.decode().split()[2]), int(up.decode().split()[4])
    y_down1, y_down2 = int(down.decode().split()[2]), int(down.decode().split()[4])
    assert y_up1 > y_up2
    assert y_down1 < y_down2


def test_hid_attach_check_reports_missing_gadget_on_first_swipe():
    serial = FakeSerial([b"ERR usb send failed\n"])
    assert check_hid_attach(serial, 494, 1019, wait_s=0.2) is False
    assert len(serial.written) == 1


def test_hid_attach_check_reports_missing_gadget_on_second_swipe():
    serial = FakeSerial([b"DONE\n", b"ERR usb send failed\n"])
    assert check_hid_attach(serial, 494, 1019, wait_s=0.2) is False
    assert len(serial.written) == 2
