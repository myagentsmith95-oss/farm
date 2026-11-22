"""Evidence layout: hardware-derived names, all cards, bounded retention."""
import json
from pathlib import Path

from farm.contracts.frame import Frame, FrameSource

from tools.capture_evidence import (
    capture_frame,
    frame_filename,
    prune_runs,
    safe_name,
    write_manifest,
)


def test_safe_name_uses_hardware_role_and_ids():
    assert safe_name("hid", "usb-1a86_USB_Single_Serial_5C63001367-if00") == (
        "hid-5C63001367"
    )
    name = safe_name("card", "534d:2109", "pci-0000:0a:00.0-usb-0:2:1.0")
    assert name.startswith("card-534d-2109-")
    assert "/" not in name and ":" not in name


def test_frame_filename_describes_the_moment():
    assert frame_filename("before") == "before.jpg"
    assert frame_filename("up") == "after-swipe-up.jpg"
    assert frame_filename("down") == "after-swipe-down.jpg"


def test_write_manifest_keeps_full_identifiers(tmp_path):
    boards = [{"serial": "5C63001367", "by_id": "usb-1a86_...-if00", "port": "/dev/ttyACM1"}]
    cards = [{"by_id": "usb-534d:2109-port", "by_path": "port", "video_dev": "/dev/video0"}]
    write_manifest(tmp_path, boards, cards)
    data = json.loads((tmp_path / "manifest.json").read_text())
    assert data["boards"] == boards
    assert data["cards"] == cards
    readme = (tmp_path / "README.txt").read_text()
    assert "5C63001367" in readme and "/dev/video0" in readme


def test_capture_frame_writes_the_frame_bytes(tmp_path):
    frame = Frame(width=2, height=2, captured_ns=1, source=FrameSource.UVC, data=b"jpeg")
    target = tmp_path / frame_filename("before")
    capture_frame(lambda: frame, target)
    assert target.read_bytes() == b"jpeg"


def test_prune_runs_keeps_only_newest(tmp_path):
    for name in ("2026-11-22T10-00-00", "2026-11-22T11-00-00", "2026-11-22T12-00-00"):
        (tmp_path / name).mkdir()
    prune_runs(tmp_path, keep=2)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "2026-11-22T11-00-00",
        "2026-11-22T12-00-00",
    ]
