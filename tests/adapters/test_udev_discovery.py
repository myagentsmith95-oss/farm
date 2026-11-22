"""Stable hardware discovery: no hardcoded /dev/videoN, no webcam confusion."""
from farm.adapters.udev import (
    is_webcam,
    physical_key,
    synthesize_by_id,
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
