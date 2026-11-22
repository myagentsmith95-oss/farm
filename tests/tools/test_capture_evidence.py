"""Evidence layout: explicit pairing, hardware names, three states per device."""
import json

import pytest

from farm.contracts.frame import Frame, FrameSource
from tools.capture_evidence import (
    capture_frame,
    capture_sequence,
    device_folder,
    frame_filename,
    match_card,
    parse_map,
    prune_runs,
    resolve_pairs,
    write_manifest,
)

BOARDS = [
    {"serial": "5C63001367", "by_id": "usb-1a86_...51367-if00", "port": "/dev/ttyACM1"},
    {"serial": "5C63002523", "by_id": "usb-1a86_...02523-if00", "port": "/dev/ttyACM0"},
]
CARDS = [
    {
        "by_id": "usb-534d:2109-pci-0000:0a:00.0-usb-0:2:1.0",
        "by_path": "pci-0000:0a:00.0-usb-0:2:1.0",
        "video_dev": "/dev/video0",
        "vendor_id": "534d",
        "product_id": "2109",
    },
    {
        "by_id": "usb-534d:2109-pci-0000:00:1d.0-usb-0:1.3.1.1:1.0",
        "by_path": "pci-0000:00:1d.0-usb-0:1.3.1.1:1.0",
        "video_dev": "/dev/video4",
        "vendor_id": "534d",
        "product_id": "2109",
    },
]


def test_safe_label_uses_hardware_role_and_ids():
    name = device_folder(BOARDS[0], CARDS[0])
    assert name.startswith("device-5C63001367--card-534d-2109-")
    assert "/" not in name and ":" not in name


def test_frame_filenames_are_three_states():
    assert frame_filename("current") == "01-current.jpg"
    assert frame_filename("swipe1") == "02-after-swipe-1.jpg"
    assert frame_filename("swipe2") == "03-after-swipe-2.jpg"


def test_parse_map_accepts_serial_equals_card():
    assert parse_map(["5C63001367=pci-0000:0a:00.0-usb-0:2:1.0"]) == {
        "5C63001367": "pci-0000:0a:00.0-usb-0:2:1.0"
    }


def test_parse_map_rejects_malformed_entry():
    with pytest.raises(ValueError):
        parse_map(["5C63001367"])


def test_match_card_by_path_or_fragment():
    assert match_card(CARDS, CARDS[0]["by_path"]) == CARDS[0]
    assert match_card(CARDS, "1d.0") == CARDS[1]
    assert match_card(CARDS, "missing") is None


def test_resolve_pairs_preserves_mapping_and_rejects_unknown():
    pairs = resolve_pairs(BOARDS, CARDS, {"5C63001367": "0a:00.0", "5C63002523": "1d.0"})
    assert [p[0]["serial"] for p in pairs] == ["5C63001367", "5C63002523"]
    assert [p[1]["video_dev"] for p in pairs] == ["/dev/video0", "/dev/video4"]
    with pytest.raises(ValueError):
        resolve_pairs(BOARDS, CARDS, {"NOPE": "0a:00.0"})


def test_write_manifest_keeps_full_identifiers(tmp_path):
    write_manifest(tmp_path, BOARDS, CARDS, {"5C63001367": "0a:00.0"})
    data = json.loads((tmp_path / "manifest.json").read_text())
    assert data["mapping"] == {"5C63001367": "0a:00.0"}
    assert data["boards"] == BOARDS
    readme = (tmp_path / "README.txt").read_text()
    assert "5C63001367" in readme and "/dev/video0" in readme


def test_capture_frame_writes_the_frame_bytes(tmp_path):
    frame = Frame(width=2, height=2, captured_ns=1, source=FrameSource.UVC, data=b"jpeg")
    target = tmp_path / frame_filename("current")
    capture_frame(lambda: frame, target)
    assert target.read_bytes() == b"jpeg"


def test_capture_sequence_waits_between_every_step(tmp_path):
    sleeps: list[float] = []
    swipes: list[tuple[int, int]] = []
    frames: list[str] = []

    def swipe(handle, x, y1, y2, ms):
        swipes.append((y1, y2))
        return True

    def grab():
        frames.append("grab")
        return Frame(width=2, height=2, captured_ns=1, source=FrameSource.UVC, data=b"jpeg")

    capture_sequence(
        object(),
        swipe,
        grab,
        tmp_path,
        resolution=(494, 1019),
        settle=0.3,
        between=0.4,
        sleep=sleeps.append,
    )
    # mid-screen swipe up, down, up: home → app drawer → home
    assert sleeps == [0.3, 0.4, 0.3, 0.4, 0.3]
    assert swipes == [(764, 255), (255, 764), (764, 255)]
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "01-current.jpg",
        "02-after-swipe-1.jpg",
        "03-after-swipe-2.jpg",
    ]
    assert frames == ["grab", "grab", "grab"]


def test_prune_runs_keeps_only_newest(tmp_path):
    for name in ("2026-11-22T10-00-00", "2026-11-22T11-00-00", "2026-11-22T12-00-00"):
        (tmp_path / name).mkdir()
    prune_runs(tmp_path, keep=2)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "2026-11-22T11-00-00",
        "2026-11-22T12-00-00",
    ]
