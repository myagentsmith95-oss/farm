"""Serial protocol v1: golden vectors and the ESP32 adapter, without hardware."""
import json
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

VECTORS = json.loads(
    (Path(__file__).resolve().parents[2] / "protocol" / "serial_vectors.json").read_text(
        encoding="utf-8"
    )
)
CASES = VECTORS["cases"]


def make_backend():
    serial = FakeEsp32Serial()
    return serial, Esp32SerialBackend(serial, width=494, height=1019, timeout_s=0.05)


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
