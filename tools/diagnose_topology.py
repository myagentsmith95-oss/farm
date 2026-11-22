#!/usr/bin/env python3
"""Authoritative host diagnostic: boards, cards, signal state and topology changes.

Exit code 0 means every discovered board answered READY and every card has a
stable active-area crop. 1 means at least one device is not usable.
"""
import argparse
import json
import time
from pathlib import Path

from farm.adapters.esp32_serial import open_esp32_no_reset
from farm.adapters.udev import (
    diff_snapshots,
    enumerate_capture_cards,
    enumerate_esp32,
    topology_snapshot,
)
from farm.adapters.uvc_cv2 import UvcCaptureSource, stable_area
from farm.contracts.errors import StaleFrame


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
        return "ERROR", None, f"{type(exc).__name__}: {exc}"
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
    args = parser.parse_args()

    boards = enumerate_esp32()
    cards = enumerate_capture_cards()
    print(f"discovered {len(boards)} ESP32 board(s), {len(cards)} capture card(s)")

    healthy = True
    for board in boards:
        ready, boots = probe_board(board.port, args.board_seconds)
        status = "READY" if ready else "NO_READY"
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
