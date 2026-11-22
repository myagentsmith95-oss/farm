#!/usr/bin/env python3
"""Drive the 26 serial-v1 golden vectors against a real ESP32 board.

"Golden" means protocol/serial_vectors.json is the single source of truth for
both the Python encoder and the firmware. This tool checks the third leg: the
firmware actually answers each documented host line with the documented reply.

The runner is lockstep and read-only with respect to the board — it never
resets it. It opens the port through open_esp32_no_reset(), handshakes with
PING, and compares replies verbatim. An unexpected BOOT during the run is a
failure (the board reset), not a vector result.

Exit codes: 0 all vectors passed, 1 at least one failed, 2 setup error.
"""
from __future__ import annotations

import argparse
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from farm.adapters.esp32_serial import open_esp32_no_reset
from farm.adapters.udev import enumerate_esp32

DEFAULT_SERIAL = "5C63001367"
DEFAULT_VECTORS = Path(__file__).resolve().parents[1] / "protocol" / "serial_vectors.json"


@dataclass(frozen=True)
class CaseResult:
    id: str
    host: str | None
    expected: str
    actual: str
    ok: bool


def load_vectors(path: Path | None = None) -> dict[str, Any]:
    target = DEFAULT_VECTORS if path is None else path
    return json.loads(target.read_text(encoding="utf-8"))


def _field(obj: object, name: str) -> object:
    """Read a field from either a mapping (tests) or a udev dataclass (live)."""
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


def resolve_board(boards: Sequence[object], serial: str) -> object:
    """Pick one board by the stable serial from its by-id name."""
    matches = [b for b in boards if _field(b, "serial") == serial]
    if not matches:
        raise ValueError(f"no ESP32 board with serial {serial!r} is connected")
    return matches[0]


def port_of(board: object) -> str:
    return str(_field(board, "port"))


def _meaningful(handle, timeout_s: float, poll_s: float, boots: list[str]) -> str | None:
    """Return the first non-log reply line; collect BOOT banners separately."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        raw = handle.readline()
        if raw:
            text = raw.decode("utf-8", errors="ignore").strip()
            if not text or text.startswith("#"):
                continue
            if text.startswith("BOOT "):
                boots.append(text)
                continue
            return text
        time.sleep(poll_s)
    return None


def _write_and_read(
    handle, line: str, timeout_s: float, poll_s: float, boots: list[str]
) -> str | None:
    handle.write((line + "\n").encode("ascii"))
    return _meaningful(handle, timeout_s, poll_s, boots)


def _handshake(handle, timeout_s: float, poll_s: float) -> None:
    """Re-PING until READY, ignoring the cold-boot BOOT banner and log lines."""
    deadline = time.monotonic() + timeout_s
    next_ping = 0.0
    while time.monotonic() < deadline:
        if time.monotonic() >= next_ping:
            handle.write(b"PING\n")
            next_ping = time.monotonic() + 0.5
        raw = handle.readline()
        if raw:
            text = raw.decode("utf-8", errors="ignore").strip()
            if text == "READY":
                return
        else:
            time.sleep(poll_s)
    raise RuntimeError("timeout waiting for READY")


def run_vectors(
    handle,
    cases: Sequence[Mapping[str, Any]],
    *,
    timeout_s: float = 15.0,
    poll_s: float = 0.01,
) -> list[CaseResult]:
    """Run every vector in file order against one already-chosen board.

    The coordinate space is re-declared whenever the case's expected `res`
    differs from the space the firmware is currently in. This keeps each case
    independent — notably after `RES 65535 65535` succeeds and would otherwise
    make the out-of-range TAP/SWIPE cases pass for the wrong reason.
    """
    boots: list[str] = []
    _handshake(handle, timeout_s, poll_s)
    current_res: tuple[int, int] | None = None
    results: list[CaseResult] = []
    invalidated = False
    for case in cases:
        expected = str(case["board"])
        host = case.get("host")
        if host is None:
            # BOOT is board-initiated. A healthy run sees none; that is the pass.
            actual = "no unexpected BOOT" if not boots else "; ".join(boots)
            results.append(CaseResult(case["id"], None, expected, actual, not boots))
            continue

        boots_before = len(boots)
        res = tuple(case["res"])
        if current_res != res:
            setup = _write_and_read(
                handle, f"RES {res[0]} {res[1]}", timeout_s, poll_s, boots
            )
            if setup != "OK":
                actual = f"setup RES failed: {setup or 'TIMEOUT'}"
                if len(boots) > boots_before:
                    invalidated = True
                results.append(CaseResult(case["id"], str(host), expected, actual, False))
                continue
            current_res = res

        actual = _write_and_read(handle, str(host), timeout_s, poll_s, boots) or "TIMEOUT"
        if len(boots) > boots_before:
            # The board reset: its replies from here on are untrustworthy.
            invalidated = True
        results.append(
            CaseResult(case["id"], str(host), expected, actual, actual == expected and not invalidated)
        )

        if case["id"].startswith("res_") and actual == "OK":
            current_res = (int(case["command"]["w"]), int(case["command"]["h"]))
    return results


def print_results(results: Sequence[CaseResult]) -> None:
    print(f"  {'case':26} {'expected':24} {'actual':24} result")
    for r in results:
        print(f"  {r.id:26} {r.expected:24} {r.actual:24} {'PASS' if r.ok else 'FAIL'}")
    passed = sum(r.ok for r in results)
    print(f"\n{passed}/{len(results)} vectors passed")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default=DEFAULT_SERIAL, help="board serial from by-id name")
    parser.add_argument("--port", help="explicit serial port (overrides --serial discovery)")
    parser.add_argument("--vectors", type=Path, default=DEFAULT_VECTORS)
    parser.add_argument(
        "--timeout", type=float, default=15.0, help="seconds per reply (covers 10 s swipe)"
    )
    args = parser.parse_args(argv)

    try:
        vectors = load_vectors(args.vectors)
        if args.port:
            port = args.port
            label = args.port
        else:
            board = resolve_board(enumerate_esp32(), args.serial)
            port, label = port_of(board), str(_field(board, "serial"))
        handle = open_esp32_no_reset(port, baud=115200, timeout=0.2)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"setup error: {exc}")
        return 2

    print(f"board {label} at {port} — {len(vectors['cases'])} golden vectors")
    try:
        results = run_vectors(handle, vectors["cases"], timeout_s=args.timeout)
    except (RuntimeError, OSError) as exc:
        print(f"run aborted: {exc}")
        return 1
    finally:
        handle.close()

    print_results(results)
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
