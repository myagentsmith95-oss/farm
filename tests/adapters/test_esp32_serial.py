"""Serial protocol v1: golden vectors and the ESP32 adapter, without hardware."""
import json
import sys
import time
import types
from collections import deque
from pathlib import Path

import pytest

from farm.adapters import esp32_serial
from farm.adapters.esp32_serial import (
    Esp32SerialBackend,
    decode_reply,
    encode_command,
    open_esp32_no_reset,
)
from farm.contracts.actions import Key, Swipe, Tap, Text
from farm.contracts.errors import InputError, UnsupportedAction
from farm.testing.fake_serial import FakeEsp32Serial
from tests.contracts.input_backend_suite import InputBackendContract

VECTORS = json.loads(
    (Path(__file__).resolve().parents[2] / "protocol" / "serial_vectors.json").read_text(
        encoding="utf-8"
    )
)
CASES = VECTORS["cases"]


def make_backend():
    serial = FakeEsp32Serial()
    return serial, Esp32SerialBackend(serial, width=494, height=1019, timeout_s=0.05)


class ResponsiveSerial(FakeEsp32Serial):
    """Firmware-shaped replies; can miss the first N PINGs (cold boot)."""

    def __init__(self, pings_before_ready: int = 0) -> None:
        super().__init__()
        self.pings = 0
        self.pings_before_ready = pings_before_ready

    def write(self, data: bytes) -> int:
        result = super().write(data)
        if data == b"PING\n":
            self.pings += 1
            if self.pings > self.pings_before_ready:
                self.feed("READY")
        elif data.startswith(b"RES "):
            self.feed("OK")
        elif data.startswith(b"TAP") or data.startswith(b"SWIPE"):
            self.feed("DONE")
        return result


class DelayedDoneSerial(FakeEsp32Serial):
    def __init__(self, delay_s: float) -> None:
        super().__init__()
        self.delay_s = delay_s
        self.wrote_at: float | None = None
        self.delivered = False

    def write(self, data: bytes) -> int:
        result = super().write(data)
        self.wrote_at = time.monotonic()
        return result

    def readline(self) -> bytes:
        if (
            not self.delivered
            and self.wrote_at is not None
            and time.monotonic() - self.wrote_at >= self.delay_s
        ):
            self.delivered = True
            return b"DONE\n"
        return b""


class ChoppedSerial(FakeEsp32Serial):
    """Returns partial lines, like a pyserial read that hits its own timeout."""

    def __init__(self, chunks: list[bytes]) -> None:
        super().__init__()
        self.chunks = deque(chunks)

    def readline(self) -> bytes:
        return self.chunks.popleft() if self.chunks else b""


def test_vectors_are_well_formed():
    assert VECTORS["protocol"] == "serial_v1"
    ids = [case["id"] for case in CASES]
    assert len(ids) == len(set(ids)) == 26
    for case in CASES:
        assert {"id", "res", "command", "host", "board"} <= set(case)
        if case["host"] is None:
            assert case["id"] == "boot_banner"
        else:
            assert case["host"] == case["command"].get("line", case["host"])


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["host"] is not None], ids=lambda c: c["id"]
)
def test_encoder_matches_every_host_vector(case):
    assert encode_command(case["command"]) == case["host"]


@pytest.mark.parametrize(
    "line, kind",
    [
        ("READY", "READY"),
        ("OK", "OK"),
        ("DONE", "DONE"),
        ("ERR bad resolution", "ERR"),
        ("ERR out of range", "ERR"),
        ("ERR unknown command", "ERR"),
        ("ERR line too long", "ERR"),
        ("ERR", "ERR"),
        ("BOOT touch-fw-2", "BOOT"),
        ("# RECV: PING", "LOG"),
        ("", None),
    ],
)
def test_decode_reply(line, kind):
    assert decode_reply(line) == kind


def test_handshake_and_resolution_use_lockstep_replies():
    serial, backend = make_backend()
    serial.feed("READY")
    backend.handshake()
    assert serial.sent == [b"PING\n"]

    serial.feed("OK")
    backend.sync_resolution()
    assert serial.sent[-1] == b"RES 494 1019\n"


def test_perform_tap_converts_normalized_coordinates_and_blocks_until_done():
    serial, backend = make_backend()
    serial.feed("DONE")
    backend.perform(Tap(x=0.5, y=0.5))
    assert serial.sent == [b"TAP 247 510\n"]


def test_perform_swipe_converts_all_four_coordinates():
    serial, backend = make_backend()
    serial.feed("DONE")
    backend.perform(Swipe(x1=0, y1=1, x2=1, y2=0, duration_ms=250))
    assert serial.sent == [b"SWIPE 0 1019 494 0 250\n"]


def test_swipe_below_firmware_minimum_is_rejected_before_sending():
    serial, backend = make_backend()
    with pytest.raises(ValueError):
        backend.perform(Swipe(x1=0, y1=0, x2=1, y2=1, duration_ms=15))
    assert serial.sent == []


def test_only_tap_and_swipe_are_supported():
    _, backend = make_backend()
    assert backend.supports(Tap(x=0.5, y=0.5)) is True
    assert backend.supports(Swipe(x1=0, y1=0, x2=1, y2=1, duration_ms=250)) is True
    assert backend.supports(Key(code="HOME")) is False
    assert backend.supports(Text(value="hi")) is False


def test_unsupported_action_raises_without_sending():
    serial, backend = make_backend()
    with pytest.raises(UnsupportedAction):
        backend.perform(Key(code="HOME"))
    assert serial.sent == []


def test_error_reply_becomes_input_error():
    serial, backend = make_backend()
    serial.feed("ERR out of range")
    with pytest.raises(InputError, match="out of range"):
        backend.perform(Tap(x=0, y=0))


def test_unexpected_boot_is_reported_and_flagged():
    serial, backend = make_backend()
    serial.feed("BOOT touch-fw-2")
    with pytest.raises(InputError, match="reset"):
        backend.perform(Tap(x=0, y=0))
    assert backend.needs_rehandshake is True


def test_missing_reply_times_out_as_input_error():
    _, backend = make_backend()
    with pytest.raises(InputError, match="timeout"):
        backend.perform(Tap(x=0, y=0))


def test_perform_after_close_raises_input_error():
    serial, backend = make_backend()
    backend.close()
    with pytest.raises(InputError):
        backend.perform(Tap(x=0, y=0))
    assert serial.sent == []


def test_open_sequence_preconfigures_then_opens_with_rts_first(monkeypatch):
    calls = []
    monkeypatch.setattr(esp32_serial, "_preconfigure_port", lambda port: calls.append(("preconfigure", port)))

    def fake_open(port, baud, timeout):
        calls.append(("open", port, baud, timeout))
        return object()

    monkeypatch.setattr(esp32_serial, "_open_pyserial", fake_open)
    result = open_esp32_no_reset("/dev/serial/by-id/x", baud=115200, timeout=1)
    assert result is not None
    assert calls[0][0] == "preconfigure"
    assert calls[1] == ("open", "/dev/serial/by-id/x", 115200, 1)


def test_pyserial_open_drops_rts_before_dtr_and_drains_stale_input(monkeypatch):
    class FakeHandle:
        port = baudrate = timeout = dsrdtr = None

        def __init__(self):
            self.order = []

        @property
        def rts(self):
            return self._rts

        @rts.setter
        def rts(self, value):
            self.order.append("rts")
            self._rts = value

        @property
        def dtr(self):
            return self._dtr

        @dtr.setter
        def dtr(self, value):
            self.order.append("dtr")
            self._dtr = value

        def open(self):
            self.order.append("open")

        def reset_input_buffer(self):
            self.order.append("drain")

    handle = FakeHandle()
    monkeypatch.setitem(sys.modules, "serial", types.SimpleNamespace(Serial=lambda: handle))
    result = esp32_serial._open_pyserial("/dev/x", 115200, 1.0)
    assert result is handle
    assert handle.dsrdtr is False
    assert handle.order == ["open", "rts", "dtr", "drain"]


class TestEsp32SerialContract(InputBackendContract):
    def make_backend(self):
        return Esp32SerialBackend(
            ResponsiveSerial(), width=494, height=1019, timeout_s=0.05
        )


def test_sync_resolution_updates_the_coordinate_space():
    serial, backend = make_backend()
    serial.feed("OK")
    backend.sync_resolution(800, 600)
    serial.feed("DONE")
    backend.perform(Tap(x=1, y=1))
    assert serial.sent == [b"RES 800 600\n", b"TAP 800 600\n"]


def test_handshake_repings_until_ready():
    serial = ResponsiveSerial(pings_before_ready=2)
    backend = Esp32SerialBackend(serial, 494, 1019, timeout_s=1.5)
    backend.handshake()
    assert serial.pings == 3


def test_long_swipe_gets_an_extended_deadline():
    serial = DelayedDoneSerial(0.2)
    backend = Esp32SerialBackend(serial, 494, 1019, timeout_s=0.05)
    backend.perform(Swipe(x1=0, y1=0, x2=1, y2=1, duration_ms=500))


def test_swipe_duration_bounds_are_enforced_host_side():
    serial, backend = make_backend()
    swipe = Swipe(x1=0, y1=0, x2=1, y2=1, duration_ms=250)
    with pytest.raises(ValueError):
        backend.perform(swipe.model_copy(update={"duration_ms": 15}))
    with pytest.raises(ValueError):
        backend.perform(swipe.model_copy(update={"duration_ms": 10001}))
    assert serial.sent == []


def test_timeout_flags_rehandshake_and_refuses_next_send():
    serial, backend = make_backend()
    with pytest.raises(InputError, match="timeout"):
        backend.perform(Tap(x=0, y=0))
    assert backend.needs_rehandshake is True
    with pytest.raises(InputError, match="rehandshake"):
        backend.perform(Tap(x=0, y=0))
    assert len(serial.sent) == 1


def test_recover_rehandshakes_and_resyncs():
    serial = ResponsiveSerial()
    backend = Esp32SerialBackend(serial, 494, 1019, timeout_s=0.05)
    backend.needs_rehandshake = True
    backend.recover()
    assert backend.needs_rehandshake is False
    assert serial.sent == [b"PING\n", b"RES 494 1019\n"]


def test_partial_lines_are_assembled_until_lf():
    serial = ChoppedSerial([b"DO", b"NE\n"])
    backend = Esp32SerialBackend(serial, 494, 1019, timeout_s=0.05)
    backend.perform(Tap(x=0, y=0))


def test_bare_err_is_an_error_reply():
    assert decode_reply("ERR") == "ERR"
