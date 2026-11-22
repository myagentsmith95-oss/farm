#!/usr/bin/env python3
"""Authoritative host diagnostic: boards, cards, signal state and topology changes.

Exit code 0 means every discovered board answered READY and every card has a
stable active-area crop. 1 means at least one device is not usable.
"""
import argparse
import json
import time
from pathlib import Path

import serial as pyserial

from farm.adapters.esp32_serial import open_esp32_no_reset
from farm.adapters.udev import (
    diff_snapshots,
    enumerate_capture_cards,
    enumerate_esp32,
    topology_snapshot,
)
from farm.adapters.uvc_cv2 import UvcCaptureSource, stable_area
from farm.contracts.errors import StaleFrame


def classify_capture_problem(detail: str) -> str:
    """Map a capture failure to the action that actually fixes it."""
    lowered = detail.lower()
    if "cannot open" in lowered or "busy" in lowered:
        return "BUSY"
    if "no hdmi signal" in lowered:
        return "NO_SIGNAL"
    if "no active area" in lowered:
        return "BLACK"
    return "ERROR"


def force_reset(handle, wait_s: float = 8.0) -> tuple[bool, bool, int]:
    """Deliberate recovery for a hung board: reset, watch BOOT, re-PING.

    This intentionally violates the no-reset-on-open rule — it is an explicit
    recovery action, never part of normal session startup.
    """
    handle.dtr = False
    handle.rts = True
    time.sleep(0.2)
    handle.rts = False
    handle.dtr = False
    boot = False
    ready = False
    pings = 0
    next_ping = 0.0
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if time.monotonic() >= next_ping:
            handle.write(b"PING\n")
            pings += 1
            next_ping = time.monotonic() + 0.5
        line = handle.readline()
        if line:
            text = line.decode("utf-8", errors="ignore").strip()
            if text.startswith("BOOT "):
                boot = True
            if text == "READY":
                ready = True
        else:
            time.sleep(0.01)
    return boot, ready, pings


def probe_board(port: str, seconds: float) -> tuple[bool, int]:
    serial = open_esp32_no_reset(port, baud=115200, timeout=0.2)
    ready = False
    boots = 0
    try:
        serial.write(b"PING\n")
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            raw = serial.readline()
            if not raw:
                time.sleep(0.01)
                continue
            line = raw.decode("utf-8", errors="ignore").strip()
            if line == "READY":
                ready = True
            elif line.startswith("BOOT "):
                boots += 1
    finally:
        serial.close()
    return ready, boots


def probe_card(card, samples: int, interval: float, timeout: float) -> tuple[str, tuple | None, str]:
    source = UvcCaptureSource(card.video_dev, signal_timeout_s=timeout)
    areas = []
    reason = ""
    try:
        source.start()
        source.refresh()
        if source.area is not None:
            areas.append(source.area)
        for _ in range(samples - 1):
            time.sleep(interval)
            try:
                source.refresh()
                if source.area is not None:
                    areas.append(source.area)
            except StaleFrame:
                pass
        stable = stable_area(areas, min_samples=2)
        if stable is not None:
            return "ACTIVE", source.area, ""
        return "UNSTABLE", source.area, "crop did not stabilise"
    except StaleFrame as exc:
        reason = str(exc)
        return ("NO_SIGNAL" if "HDMI" in reason else "BLACK"), None, reason
    except Exception as exc:  # diagnostic tool: report, do not crash
        detail = f"{type(exc).__name__}: {exc}"
        problem = classify_capture_problem(detail)
        if problem == "BUSY":
            detail += " (close ffplay/other probes holding this card, then retry)"
        return problem, None, detail
    finally:
        source.close()


def print_snapshot_change(path: str | None, current: dict) -> None:
    if not path:
        return
    target = Path(path)
    if not target.exists():
        target.write_text(json.dumps(current, indent=2) + "\n")
        print(f"\nwrote baseline snapshot to {path}")
        return
    previous = json.loads(target.read_text())
    change = diff_snapshots(previous, current)
    print("\n== topology change since snapshot ==")
    print(f"  added:   {change['added'] or 'none'}")
    print(f"  removed: {change['removed'] or 'none'}")
    target.write_text(json.dumps(current, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", help="baseline file; created if absent, updated each run")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--signal-timeout", type=float, default=8.0)
    parser.add_argument("--board-seconds", type=float, default=1.0)
    parser.add_argument(
        "--recover",
        action="store_true",
        help="deliberately reset boards that do not answer PING (never on normal open)",
    )
    args = parser.parse_args()

    boards = enumerate_esp32()
    cards = enumerate_capture_cards()
    print(f"discovered {len(boards)} ESP32 board(s), {len(cards)} capture card(s)")

    healthy = True
    for board in boards:
        ready, boots = probe_board(board.port, args.board_seconds)
        status = "READY" if ready else "NO_READY"
        if not ready and args.recover:
            handle = pyserial.Serial(board.port, 115200, timeout=0.2, dsrdtr=False)
            try:
                boot, recovered, pings = force_reset(handle)
            finally:
                handle.close()
            status = "RECOVERED" if recovered else "STILL_NO_READY"
            print(f"\nESP32 {board.serial}  by_id={board.by_id}")
            print(f"  recovery: BOOT={boot}, PINGs={pings}, status={status}")
            healthy = healthy and recovered
            continue
        healthy = healthy and ready
        print(f"\nESP32 {board.serial}  by_id={board.by_id}")
        print(f"  status: {status}, BOOT banners in window: {boots}")

    for card in cards:
        state, area, detail = probe_card(card, args.samples, args.interval, args.signal_timeout)
        healthy = healthy and state == "ACTIVE"
        print(f"\nCARD {card.video_dev}  by_id={card.by_id}")
        print(f"  state: {state}, crop: {area}, detail: {detail or 'ok'}")

    print_snapshot_change(args.snapshot, topology_snapshot())
    print(f"\nRESULT: {'OK' if healthy else 'NOT READY'}")
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
