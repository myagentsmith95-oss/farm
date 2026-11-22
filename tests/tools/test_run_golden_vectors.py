"""Golden-vector runner: drive the 26 host lines against firmware, no hardware."""
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from farm.testing.fake_serial import FakeEsp32Serial
from tools.run_golden_vectors import (
    CaseResult,
    load_vectors,
    port_of,
    resolve_board,
    run_vectors,
)

VECTORS_PATH = Path(__file__).resolve().parents[2] / "protocol" / "serial_vectors.json"
VECTORS = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
CASES = VECTORS["cases"]


class SimulatedFirmware(FakeEsp32Serial):
    """Answers host lines with the golden replies; can inject realistic faults."""

    def __init__(
        self,
        cases: list[dict],
        *,
        cold_boot: bool = False,
        wrong: set[str] | None = None,
        silent: set[str] | None = None,
        boot_after: str | None = None,
        log: bool = False,
    ) -> None:
        super().__init__()
        self.replies = {c["host"]: c["board"] for c in cases if c["host"] is not None}
        self.wrong = set(wrong or [])
        self.silent = set(silent or [])
        self.boot_after = boot_after
        self.log = log
        self.writes: list[str] = []
        if cold_boot:
            self.feed("BOOT touch-fw-2")

    def write(self, data: bytes) -> int:
        result = super().write(data)
        line = data.decode("ascii").rstrip("\n")
        self.writes.append(line)
        if self.log:
            self.feed(f"# RECV: {line}")
        if line in self.silent:
            return result
        reply = "WRONG" if line in self.wrong else self.replies.get(line)
        if reply is not None:
            self.feed(reply)
        if self.boot_after is not None and line == self.boot_after:
            self.feed("BOOT touch-fw-2")
        return result


def _run(fw: SimulatedFirmware, **kwargs) -> list[CaseResult]:
    opts = {"timeout_s": 0.05, "poll_s": 0.001}
    opts.update(kwargs)
    return run_vectors(fw, CASES, **opts)


def test_load_vectors_has_26_cases():
    vectors = load_vectors(VECTORS_PATH)
    assert vectors["protocol"] == "serial_v1"
    assert len(vectors["cases"]) == 26


def test_all_cases_pass_against_simulated_firmware():
    results = _run(SimulatedFirmware(CASES, cold_boot=True))
    assert len(results) == 26
    assert all(r.ok for r in results), [r for r in results if not r.ok]
    assert results[-1].id == "boot_banner"
    assert results[-1].actual == "no unexpected BOOT"


def test_every_host_line_is_sent_exactly():
    fw = SimulatedFirmware(CASES)
    _run(fw)
    for case in CASES:
        if case["host"] is not None:
            assert case["host"] in fw.writes


def test_resolution_is_resynced_after_res_max():
    # RES 65535 65535 changes the firmware's coordinate space; the next
    # coordinate case must restore 494x1019 or out-of-range checks break.
    fw = SimulatedFirmware(CASES)
    _run(fw)
    idx = fw.writes.index("RES 65535 65535")
    assert "RES 494 1019" in fw.writes[idx + 1 : idx + 3]


def test_wrong_reply_fails_only_that_case():
    fw = SimulatedFirmware(CASES, wrong={"TAP 10 20"})
    bad = [r for r in _run(fw) if not r.ok]
    assert [r.id for r in bad] == ["tap_default_hold"]
    assert bad[0].actual == "WRONG"


def test_missing_reply_times_out_and_fails():
    fw = SimulatedFirmware(CASES, silent={"TAP 247 509"})
    bad = [r for r in _run(fw, timeout_s=0.02) if not r.ok]
    assert [r.id for r in bad] == ["tap_center"]
    assert bad[0].actual == "TIMEOUT"


def test_unexpected_boot_fails_the_run():
    fw = SimulatedFirmware(CASES, boot_after="TAP 0 0")
    results = _run(fw)
    assert any(not r.ok for r in results)
    assert results[-1].ok is False
    assert results[-1].actual == "BOOT touch-fw-2"


def test_firmware_log_lines_are_ignored():
    results = _run(SimulatedFirmware(CASES, log=True))
    assert all(r.ok for r in results)


BOARDS = [
    {"serial": "5C63001367", "port": "/dev/serial/by-id/a-if00"},
    {"serial": "5C63002523", "port": "/dev/serial/by-id/b-if00"},
]


def test_resolve_board_selects_by_serial():
    board = resolve_board(BOARDS, "5C63002523")
    assert board["port"] == "/dev/serial/by-id/b-if00"


@dataclass(frozen=True)
class DeviceLike:
    serial: str
    port: str


def test_resolve_board_accepts_dataclass_devices_from_udev():
    # enumerate_esp32() returns Esp32Device dataclasses, not dicts.
    devices = [DeviceLike("5C63001367", "/dev/serial/by-id/a-if00")]
    board = resolve_board(devices, "5C63001367")
    assert port_of(board) == "/dev/serial/by-id/a-if00"


def test_resolve_board_rejects_unknown_serial():
    with pytest.raises(ValueError, match="no ESP32 board"):
        resolve_board(BOARDS, "not-a-board")
