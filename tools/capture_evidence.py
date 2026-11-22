#!/usr/bin/env python3
"""Screenshot evidence for HID checks, keyed by hardware identity.

Works for every attached capture card. The frame writer uses only the Frame
contract, so a future ADB screencap source can reuse it unchanged.
"""
from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

from farm.contracts.frame import Frame

STAGES = {
    "before": "before.jpg",
    "up": "after-swipe-up.jpg",
    "down": "after-swipe-down.jpg",
}


def safe_name(kind: str, *identifiers: str) -> str:
    """A descriptive, filename-safe label built from stable device ids."""
    parts: list[str] = []
    for value in identifiers:
        if kind == "hid" and value.startswith("usb-"):
            base = re.sub(r"-if\d+$", "", value)
            value = base.rsplit("_", 1)[-1]
        clean = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")
        if clean:
            parts.append(clean)
    return "-".join([kind, *parts])


def frame_filename(stage: str) -> str:
    """Clear filename for the moment the frame was taken."""
    return STAGES[stage]


def write_manifest(
    root: Path, boards: list[Mapping[str, str]], cards: list[Mapping[str, str]]
) -> None:
    """Write machine- and human-readable descriptions of the devices."""
    board_list = [dict(board) for board in boards]
    card_list = [dict(card) for card in cards]
    (root / "manifest.json").write_text(
        json.dumps({"boards": board_list, "cards": card_list}, indent=2) + "\n"
    )
    lines = ["# Evidence run", "", "## HID boards", ""]
    for board in board_list:
        lines.append(
            f"- {safe_name('hid', board.get('by_id', board.get('serial', 'board')))}: "
            f"serial={board.get('serial')} by_id={board.get('by_id')} port={board.get('port')}"
        )
    lines += ["", "## Capture cards", ""]
    for card in card_list:
        lines.append(
            f"- {safe_name('card', card.get('vendor_id', ''), card.get('product_id', ''), card.get('by_path', ''))}: "
            f"by_id={card.get('by_id')} by_path={card.get('by_path')} node={card.get('video_dev')}"
        )
    (root / "README.txt").write_text("\n".join(lines) + "\n")


def capture_frame(grab: Callable[[], Frame], target: Path) -> None:
    """Store the encoded frame bytes. No UVC/ADB specifics here."""
    frame = grab()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(frame.data)


def prune_runs(base: Path, keep: int) -> None:
    """Keep only the newest `keep` timestamped run folders."""
    runs = sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name)
    for old in runs[:-keep] if keep > 0 else runs:
        for child in sorted(old.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        old.rmdir()


def run(base: Path, keep: int = 5, resolution: tuple[int, int] = (494, 1019)) -> Path:
    """Capture before/up/down frames from every card for every board."""
    from farm.adapters.udev import enumerate_capture_cards, enumerate_esp32
    from farm.adapters.uvc_cv2 import UvcCaptureSource
    from tools.diagnose_topology import open_board, swipe_step

    root = base / datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    root.mkdir(parents=True, exist_ok=True)
    boards = enumerate_esp32()
    cards = enumerate_capture_cards()
    write_manifest(
        root,
        [{"serial": b.serial, "by_id": b.by_id, "port": b.port} for b in boards],
        [
            {
                "by_id": c.by_id,
                "by_path": c.by_path,
                "video_dev": c.video_dev,
                "vendor_id": c.vendor_id,
                "product_id": c.product_id,
            }
            for c in cards
        ],
    )

    def grab_all(stage: str, board_label: str | None = None) -> None:
        for card in cards:
            source = UvcCaptureSource(card.video_dev)
            try:
                source.start()

                def grab() -> Frame:
                    source.refresh()
                    return source.latest(0)

                folder = safe_name(
                    "card", card.vendor_id, card.product_id, card.by_path
                )
                parts = [stage]
                if board_label:
                    parts.append(board_label)
                parts.append(folder)
                capture_frame(grab, root.joinpath(*parts) / frame_filename(stage))
            finally:
                source.close()

    grab_all("before")
    x = int(0.5 * resolution[0] + 0.5)
    low = int(0.75 * resolution[1] + 0.5)
    high = int(0.25 * resolution[1] + 0.5)
    for board in boards:
        label = safe_name("hid", board.by_id)
        handle = open_board(board.port)
        try:
            for stage, (y1, y2) in (
                ("up", (low, high)),
                ("down", (high, low)),
            ):
                swipe_step(handle, x, y1, y2, 500)
                grab_all(stage, label)
        finally:
            handle.close()
    prune_runs(base, keep)
    return root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", default="var/evidence", help="evidence root")
    parser.add_argument("--keep", type=int, default=5)
    parser.add_argument("--resolution", nargs=2, type=int, default=(494, 1019))
    args = parser.parse_args()
    root = run(Path(args.evidence), args.keep, tuple(args.resolution))
    print(f"evidence written to {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
