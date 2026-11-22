"""Stable hardware discovery: no hardcoded /dev/videoN, no webcam confusion."""
from farm.adapters.udev import (
    diff_snapshots,
    is_webcam,
    physical_key,
    synthesize_by_id,
    topology_snapshot,
)


def test_physical_key_from_v4l_bypath():
    assert physical_key("pci-0000:0a:00.0-usb-0:2:1.0-video-index0") == (
        "pci-0000:0a:00.0-usb-0:2:1.0"
    )


def test_physical_key_rejects_metadata_and_other_names():
    assert physical_key("pci-0000:0a:00.0-usbv2-0:2:1.0-video-index0") is None
    assert physical_key("usb-1a86_foo-if00") is None


def test_webcam_is_filtered_by_name():
    assert is_webcam("Laptop_Integrated_Webcam_FHD: I")
    assert is_webcam("Integrated Camera")
    assert not is_webcam("USB Video: USB Video")
    assert not is_webcam("MacroSilicon MS2109")


def test_synthesized_by_id_is_unique_per_physical_port():
    first = synthesize_by_id("534d", "2109", "pci-0000:0a:00.0-usb-0:2:1.0")
    second = synthesize_by_id("534d", "2109", "pci-0000:00:1a.0-usb-0:1.5:1.0")
    assert first.startswith("usb-534d:2109-")
    assert first != second


def test_synthesized_by_id_is_nonblank():
    assert synthesize_by_id("0000", "0000", "port")


def test_snapshot_is_a_stable_sorted_structure():
    snap = topology_snapshot()
    assert set(snap) == {"esp32", "cards"}
    assert snap["esp32"] == sorted(snap["esp32"])
    assert snap["cards"] == sorted(snap["cards"])


def test_diff_reports_added_removed_and_changed_devices():
    old = {"esp32": ["board-a"], "cards": ["card-a"]}
    new = {"esp32": ["board-b"], "cards": ["card-a", "card-b"]}
    result = diff_snapshots(old, new)
    assert result["added"] == ["board-b", "card-b"]
    assert result["removed"] == ["board-a"]
    assert result["changed"] == []


def test_diff_detects_a_port_change_for_the_same_card():
    old = {"esp32": [], "cards": ["usb-534d:2109-port1"]}
    new = {"esp32": [], "cards": ["usb-534d:2109-port2"]}
    result = diff_snapshots(old, new)
    assert "usb-534d:2109-port1" in result["removed"]
    assert "usb-534d:2109-port2" in result["added"]
