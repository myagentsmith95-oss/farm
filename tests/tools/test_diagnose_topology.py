"""Diagnostic helpers: classify failures and recover a hung board."""
from collections import deque

from tools.diagnose_topology import classify_capture_problem, force_reset


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
    boot, ready, pings = force_reset(serial, wait_s=0.1)
    assert boot is True and ready is True and pings >= 1
    assert serial.written[0] == b"PING\n"
    assert serial.dtr is False and serial.rts is False
