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


def missing_expected(expected: dict, current: dict) -> list[str]:
    """Known identities that disappeared — a vanished device is a failure."""
    missing: list[str] = []
    for kind in ("esp32", "cards"):
        missing.extend(sorted(set(expected.get(kind, [])) - set(current.get(kind, []))))
    return missing


def classify_tap(line: str) -> str:
    if line == "DONE":
        return "DONE"
    if line.startswith("ERR"):
        return "ERR"
    return "OTHER"


def _wait_for_done(handle, wait_s: float) -> bool:
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        raw = handle.readline()
        if raw:
            kind = classify_tap(raw.decode("utf-8", errors="ignore").strip())
            if kind == "DONE":
                return True
            if kind == "ERR":
                return False
        else:
            time.sleep(0.01)
    return False


def check_hid_attach(handle, width: int, height: int, wait_s: float = 5.0) -> bool:
    """Swipe up then down: DONE for both proves the HID gadget reaches a phone.

    A vertical pair also exercises the digitizer's movement path, not just a
    single touch-down, and may wake a sleeping screen.
    """
    x = int(0.5 * width + 0.5)
    low = int(0.75 * height + 0.5)
    high = int(0.25 * height + 0.5)
    for y1, y2 in ((low, high), (high, low)):
        handle.write(f"SWIPE {x} {y1} {x} {y2} 500\n".encode("ascii"))
        if not _wait_for_done(handle, wait_s):
            return False
    return True


def force_reset(
    handle,
    wait_s: float = 8.0,
    resolution: tuple[int, int] | None = None,
) -> tuple[bool, bool, int, bool]:
    """Deliberate recovery: reset, watch BOOT, re-PING, re-send RES.

    This intentionally violates the no-reset-on-open rule — it is an explicit
    recovery action, never part of normal session startup. Without `resolution`
    the caller must re-sync RES before any touch is injected.
    """
    handle.dtr = False
    handle.rts = True
    time.sleep(0.2)
    handle.rts = False
    handle.dtr = False
    boot = False
    ready = False
    res_ok = False
    res_sent = False
    pings = 0
    next_ping = 0.0
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if not ready and time.monotonic() >= next_ping:
            handle.write(b"PING\n")
            pings += 1
            next_ping = time.monotonic() + 0.5
        if ready and resolution is not None and not res_sent:
            handle.write(f"RES {resolution[0]} {resolution[1]}\n".encode("ascii"))
            res_sent = True
        line = handle.readline()
        if line:
            text = line.decode("utf-8", errors="ignore").strip()
            if text.startswith("BOOT "):
                boot = True
            if text == "READY":
                ready = True
            if text == "OK" and res_sent:
                res_ok = True
        else:
            time.sleep(0.01)
    return boot, ready, pings, res_ok


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


def print_snapshot_change(path: str | None, current: dict) -> bool:
    """Report changes; False when a previously known device disappeared.

    The baseline is not overwritten while something is missing, so the failure
    stays visible until the operator fixes the hardware and acknowledges it.
    """
    if not path:
        return True
    target = Path(path)
    if not target.exists():
        target.write_text(json.dumps(current, indent=2) + "\n")
        print(f"\nwrote baseline snapshot to {path}")
        return True
    previous = json.loads(target.read_text())
    change = diff_snapshots(previous, current)
    missing = missing_expected(previous, current)
    print("\n== topology change since snapshot ==")
    print(f"  added:   {change['added'] or 'none'}")
    print(f"  removed: {change['removed'] or 'none'}")
    print(f"  MISSING: {missing or 'none'}")
    if missing:
        return False
    target.write_text(json.dumps(current, indent=2) + "\n")
    return True


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
    parser.add_argument(
        "--resolution",
        nargs=2,
        type=int,
        metavar=("W", "H"),
        help="crop size to re-send as RES after recovery and for the HID check",
    )
    parser.add_argument(
        "--check-hid",
        action="store_true",
        help="send one centre TAP per READY board to prove the HID gadget reaches a phone",
    )
    args = parser.parse_args()
    resolution = tuple(args.resolution) if args.resolution else None

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
                boot, recovered, pings, res_ok = force_reset(handle, resolution=resolution)
            finally:
                handle.close()
            if recovered and resolution is not None and not res_ok:
                status = "RES_FAILED"
            else:
                status = "RECOVERED" if recovered else "STILL_NO_READY"
            print(f"\nESP32 {board.serial}  by_id={board.by_id}")
            print(
                f"  recovery: BOOT={boot}, PINGs={pings}, RES={res_ok}, status={status}"
            )
            healthy = healthy and status == "RECOVERED"
            continue
        healthy = healthy and ready
        print(f"\nESP32 {board.serial}  by_id={board.by_id}")
        print(f"  status: {status}, BOOT banners in window: {boots}")
        if ready and args.check_hid:
            width, height = resolution or (720, 1480)
            handle = pyserial.Serial(board.port, 115200, timeout=0.2, dsrdtr=False)
            try:
                attached = check_hid_attach(handle, width, height)
            finally:
                handle.close()
            print(f"  HID attach: {'DONE' if attached else 'FAILED (usb send failed?)'}")
            healthy = healthy and attached

    for card in cards:
        state, area, detail = probe_card(card, args.samples, args.interval, args.signal_timeout)
        healthy = healthy and state == "ACTIVE"
        print(f"\nCARD {card.video_dev}  by_id={card.by_id}")
        print(f"  state: {state}, crop: {area}, detail: {detail or 'ok'}")

    topology_ok = print_snapshot_change(args.snapshot, topology_snapshot())
    healthy = healthy and topology_ok
    print(f"\nRESULT: {'OK' if healthy else 'NOT READY'}")
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
