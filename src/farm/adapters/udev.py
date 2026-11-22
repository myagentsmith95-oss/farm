"""Stable hardware discovery for the farm host (architecture §3 and C32).

Never use a hardcoded /dev/videoN: the experiments' /dev/video2 is the laptop
webcam on this host. ESP32 boards are found by by-id, capture cards by physical
USB port (by-path), and each card gets a synthesized unique by_id.
"""
from __future__ import annotations

import fcntl
import os
import re
import struct
from dataclasses import dataclass
from pathlib import Path

SERIAL_BY_ID = Path("/dev/serial/by-id")
V4L_BY_PATH = Path("/dev/v4l/by-path")
QINHENG_VENDOR = "1a86"
WEBCAM_KEYWORDS = ("webcam", "camera", "facetime", "isight")
NODE_RE = re.compile(r"^(?P<phys>.+)-video-index\d+$")

_VIDIOC_QUERYCAP = 0x80685600
_V4L2_CAP_VIDEO_CAPTURE = 0x00000001
_V4L2_CAP_DEVICE_CAPS = 0x80000000


@dataclass(frozen=True)
class Esp32Device:
    by_id: str  # stable name from /dev/serial/by-id
    port: str  # full by-id symlink path
    serial: str


@dataclass(frozen=True)
class CaptureDevice:
    by_id: str  # synthesized vendor:product + physical port (C32)
    by_path: str  # physical USB port key
    video_dev: str  # the real capture node, e.g. /dev/video0
    vendor_id: str
    product_id: str


def physical_key(link_name: str) -> str | None:
    """Extract the stable by-path key, rejecting usbv2 duplicates."""
    if "-usbv2-" in link_name:
        return None
    match = NODE_RE.match(link_name)
    return match.group("phys") if match else None


def is_webcam(card_name: str) -> bool:
    lowered = card_name.lower()
    return any(word in lowered for word in WEBCAM_KEYWORDS)


def synthesize_by_id(vendor_id: str, product_id: str, phys_key: str) -> str:
    """C32: serial-less devices get vendor:product + USB port path."""
    return f"usb-{vendor_id}:{product_id}-{phys_key}"


def _extract_serial(by_id_name: str) -> str:
    base = re.sub(r"-if\d+$", "", by_id_name)
    return base.rsplit("_", 1)[-1]


def enumerate_esp32() -> tuple[Esp32Device, ...]:
    if not SERIAL_BY_ID.is_dir():
        return ()
    devices = []
    for entry in sorted(SERIAL_BY_ID.iterdir()):
        if QINHENG_VENDOR not in entry.name:
            continue
        devices.append(
            Esp32Device(
                by_id=entry.name,
                port=str(entry),
                serial=_extract_serial(entry.name),
            )
        )
    return tuple(devices)


def enumerate_capture_cards() -> tuple[CaptureDevice, ...]:
    """Group V4L nodes by physical port, skipping webcams and metadata nodes."""
    if not V4L_BY_PATH.is_dir():
        return ()
    grouped: dict[str, list[str]] = {}
    for entry in V4L_BY_PATH.iterdir():
        key = physical_key(entry.name)
        if key is None:
            continue
        try:
            node = os.path.basename(os.readlink(entry))
        except OSError:
            continue
        grouped.setdefault(key, []).append(node)

    cards = []
    for key, nodes in sorted(grouped.items()):
        picked = None
        for node in sorted(nodes):
            if is_webcam(_card_name(node)):
                continue
            if _can_capture(node):
                picked = node
                break
        if picked is None:
            continue
        vendor, product = _usb_ids(picked)
        cards.append(
            CaptureDevice(
                by_id=synthesize_by_id(vendor, product, key),
                by_path=key,
                video_dev=f"/dev/{picked}",
                vendor_id=vendor,
                product_id=product,
            )
        )
    return tuple(cards)


def _card_name(node: str) -> str:
    try:
        return Path(f"/sys/class/video4linux/{node}/name").read_text().strip()
    except OSError:
        return ""


def _can_capture(node: str) -> bool:
    """Use VIDIOC_QUERYCAP to tell the capture node from the metadata node."""
    try:
        fd = os.open(f"/dev/{node}", os.O_RDWR | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        buf = bytearray(104)
        fcntl.ioctl(fd, _VIDIOC_QUERYCAP, buf)
        fields = struct.unpack_from("=16s32s32sIII3I", buf, 0)
        capabilities, device_caps = fields[4], fields[5]
        effective = device_caps if capabilities & _V4L2_CAP_DEVICE_CAPS else capabilities
        return bool(effective & _V4L2_CAP_VIDEO_CAPTURE)
    except OSError:
        return False
    finally:
        os.close(fd)


def _usb_ids(node: str) -> tuple[str, str]:
    """Walk sysfs from the video device up to the USB device's id files."""
    try:
        target = Path(f"/sys/class/video4linux/{node}/device").resolve()
    except OSError:
        return "0000", "0000"
    for directory in (target, *target.parents):
        vendor = directory / "idVendor"
        product = directory / "idProduct"
        if vendor.exists() and product.exists():
            try:
                return (
                    vendor.read_text().strip(),
                    product.read_text().strip(),
                )
            except OSError:
                return "0000", "0000"
    return "0000", "0000"
