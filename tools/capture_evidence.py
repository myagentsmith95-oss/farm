#!/usr/bin/env python3
"""Three-state screenshot evidence per device, keyed by hardware identity.

For each enrolled pair (ESP32 board + capture card) we capture:
  01-current.jpg, 02-after-swipe-1.jpg, 03-after-swipe-2.jpg

The board↔card pairing is explicit, not guessed from frame diffs — a swipe can
change nothing visible, so a diff cannot be trusted as authority.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

from farm.contracts.frame import Frame

# From the experiments repo hil-rig/devices/rig-*.yaml (the proven wiring).
DEFAULT_MAP = {
    "5C63001367": "pci-0000:0a:00.0-usb-0:2:1.0",
    "5C63002523": "pci-0000:00:1d.0-usb-0:1.3.1.1:1.0",
}

STAGES = {
    "current": "01-current.jpg",
    "swipe1": "02-after-swipe-1.jpg",
    "swipe2": "03-after-swipe-2.jpg",
}


def parse_map(entries: list[str] | None) -> dict[str, str]:
    """Parse repeated SERIAL=CARD_KEY arguments."""
    result: dict[str, str] = {}
    for entry in entries or []:
        if "=" not in entry:
            raise ValueError(f"expected SERIAL=CARD_KEY, got {entry!r}")
        serial, card_key = entry.split("=", 1)
        if not serial.strip() or not card_key.strip():
            raise ValueError(f"empty side in mapping {entry!r}")
        result[serial.strip()] = card_key.strip()
    return result


def safe_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")


def device_folder(board: Mapping[str, str], card: Mapping[str, str]) -> str:
    """One descriptive folder name for a seat: board serial + card identity."""
    serial = board.get("serial", board.get("by_id", "board"))
    if serial.startswith("usb-"):
        serial = re.sub(r"-if\d+$", "", serial).rsplit("_", 1)[-1]
    card_label = "-".join(
        filter(
            None,
            [card.get("vendor_id", ""), card.get("product_id", ""), card.get("by_path", "")],
        )
    )
    return f"device-{safe_part(serial)}--card-{safe_part(card_label)}"


def frame_filename(stage: str) -> str:
    return STAGES[stage]


def match_card(cards: list[Mapping[str, str]], key: str) -> Mapping[str, str] | None:
    """Match by full by-path/by-id, folder label, or a unique fragment."""
    for card in cards:
        if key in (card.get("by_path", ""), card.get("by_id", "")):
            return card
    for card in cards:
        label = "-".join(
            filter(None, [card.get("vendor_id", ""), card.get("product_id", ""), card.get("by_path", "")])
        )
        if safe_part(label) == safe_part(key):
            return card
    hits = [card for card in cards if key in card.get("by_path", "")]
    return hits[0] if len(hits) == 1 else None


def resolve_pairs(
    boards: list[Mapping[str, str]],
    cards: list[Mapping[str, str]],
    mapping: Mapping[str, str],
) -> list[tuple[Mapping[str, str], Mapping[str, str]]]:
    """Explicitly pair boards to cards; unknown serials are an error."""
    pairs = []
    for board in boards:
        serial = board.get("serial", board.get("by_id", ""))
        if serial not in mapping:
            continue
        card = match_card(cards, mapping[serial])
        if card is None:
            raise ValueError(f"no capture card matches {mapping[serial]!r} for {serial}")
        pairs.append((board, card))
    if not pairs:
        raise ValueError("no boards matched the mapping — pass --map SERIAL=CARD_KEY")
    return pairs


def write_manifest(
    root: Path,
    boards: list[Mapping[str, str]],
    cards: list[Mapping[str, str]],
    mapping: Mapping[str, str],
) -> None:
    board_list = [dict(board) for board in boards]
    card_list = [dict(card) for card in cards]
    (root / "manifest.json").write_text(
        json.dumps(
            {"mapping": dict(mapping), "boards": board_list, "cards": card_list}, indent=2
        )
        + "\n"
    )
    lines = [
        "# Evidence run",
        "",
        "Each device folder holds three states: current, after swipe 1, after swipe 2.",
        "Folder names come from stable hardware identities, never /dev/videoN.",
        "",
        "## Board ↔ card mapping (explicit, from hil-rig wiring)",
        "",
    ]
    for board in board_list:
        serial = board.get("serial", board.get("by_id", "board"))
        lines.append(f"- {serial} -> {mapping.get(serial, 'unmapped')}")
    lines += ["", "## HID boards", ""]
    for board in board_list:
        lines.append(
            f"- {board.get('serial')}: by_id={board.get('by_id')} port={board.get('port')}"
        )
    lines += ["", "## Capture cards", ""]
    for card in card_list:
        lines.append(
            f"- {card.get('by_id')}: by_path={card.get('by_path')} node={card.get('video_dev')}"
        )
    (root / "README.txt").write_text("\n".join(lines) + "\n")


def capture_frame(grab: Callable[[], Frame], target: Path) -> None:
    """Store encoded frame bytes. Contract-only: works for UVC and future ADB."""
    frame = grab()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(frame.data)


def capture_sequence(
    handle,
    swipe: Callable[[object, int, int, int, int], bool],
    grab: Callable[[], Frame],
    folder: Path,
    resolution: tuple[int, int] = (494, 1019),
    settle: float = 0.5,
    between: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Swipe up → down → up on one device, with a screenshot after each.

    On this launcher the mid-screen vertical pair toggles the app drawer:
    home screen → app drawer → home screen. It is NOT the notification shade
    (that needs a swipe from the top edge, y≈30→900). The first swipe puts the
    sequence in a known state; waits are explicit and do not depend on camera
    re-initialisation.
    """
    x = int(0.5 * resolution[0] + 0.5)
    low = int(0.75 * resolution[1] + 0.5)
    high = int(0.25 * resolution[1] + 0.5)
    # First mid-screen swipe: establish a known starting screen.
    swipe(handle, x, low, high, 500)
    sleep(settle)
    capture_frame(grab, folder / frame_filename("current"))
    sleep(between)
    # Opposite swipe: toggles the app drawer on this launcher.
    swipe(handle, x, high, low, 500)
    sleep(settle)
    capture_frame(grab, folder / frame_filename("swipe1"))
    sleep(between)
    # Third swipe: return to the starting screen.
    swipe(handle, x, low, high, 500)
    sleep(settle)
    capture_frame(grab, folder / frame_filename("swipe2"))


def prune_runs(base: Path, keep: int) -> None:
    runs = sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name)
    for old in runs[:-keep] if keep > 0 else runs:
        for child in sorted(old.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        old.rmdir()


def run(
    base: Path,
    keep: int = 5,
    resolution: tuple[int, int] = (494, 1019),
    mapping: Mapping[str, str] | None = None,
    settle: float = 0.5,
    between: float = 0.5,
    drain: int = 3,
) -> Path:
    from farm.adapters.udev import enumerate_capture_cards, enumerate_esp32
    from farm.adapters.uvc_cv2 import UvcCaptureSource
    from tools.diagnose_topology import open_board, swipe_step

    mapping = dict(mapping or DEFAULT_MAP)
    boards = [
        {"serial": b.serial, "by_id": b.by_id, "port": b.port}
        for b in enumerate_esp32()
    ]
    cards = [
        {
            "by_id": c.by_id,
            "by_path": c.by_path,
            "video_dev": c.video_dev,
            "vendor_id": c.vendor_id,
            "product_id": c.product_id,
        }
        for c in enumerate_capture_cards()
    ]
    pairs = resolve_pairs(boards, cards, mapping)
    root = base / datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    root.mkdir(parents=True, exist_ok=True)
    write_manifest(root, boards, cards, mapping)

    for board, card in pairs:
        # One source stays open for the whole three-state sequence: the waits,
        # not camera re-initialisation, control when each frame is taken.
        source = UvcCaptureSource(card["video_dev"], drain=drain)

        def grab() -> Frame:
            source.refresh()
            return source.latest(1000)

        try:
            source.start()
            handle = open_board(board["port"])
            try:
                capture_sequence(
                    handle,
                    swipe_step,
                    grab,
                    root / device_folder(board, card),
                    resolution=resolution,
                    settle=settle,
                    between=between,
                )
            finally:
                handle.close()
        finally:
            source.close()
    prune_runs(base, keep)
    return root


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", default="evidence", help="evidence root")
    parser.add_argument("--keep", type=int, default=5)
    parser.add_argument("--resolution", nargs=2, type=int, default=(494, 1019))
    parser.add_argument("--settle", type=float, default=0.5, help="wait after each swipe")
    parser.add_argument("--between", type=float, default=0.5, help="wait between states")
    parser.add_argument("--drain", type=int, default=3, help="stale frames to discard per shot")
    parser.add_argument(
        "--map",
        action="append",
        metavar="SERIAL=CARD_KEY",
        help="board serial to capture-card by-path (repeatable); defaults to hil-rig wiring",
    )
    args = parser.parse_args()
    root = run(
        Path(args.evidence),
        args.keep,
        tuple(args.resolution),
        parse_map(args.map) or None,
        settle=args.settle,
        between=args.between,
        drain=args.drain,
    )
    print(f"evidence written to {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
