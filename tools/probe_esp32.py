#!/usr/bin/env python3
"""Host probe: PING each ESP32 over the no-reset port and print its banners.

This is a diagnostic tool, not a test. It opens the port with the proven
no-reset sequence, sends one PING and listens for a short window. Any BOOT line
after the port is open is a reset and should be investigated.
"""
import argparse
import time

from farm.adapters.esp32_serial import open_esp32_no_reset
from farm.adapters.udev import enumerate_esp32


def probe(port: str, seconds: float, baud: int) -> list[str]:
    serial = open_esp32_no_reset(port, baud=baud, timeout=0.2)
    banners: list[str] = []
    try:
        serial.write(b"PING\n")
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            raw = serial.readline()
            if not raw:
                time.sleep(0.01)
                continue
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            print(f"  [esp32] {line}")
            if line.startswith("BOOT "):
                banners.append(line)
    finally:
        serial.close()
    return banners


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="by-id path; default probes all discovered boards")
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    if args.port:
        targets = [args.port]
    else:
        devices = enumerate_esp32()
        print(f"discovered {len(devices)} ESP32 board(s)")
        targets = [device.port for device in devices]

    for port in targets:
        print(f"\n== {port} ==")
        banners = probe(port, args.seconds, args.baud)
        print(f"  BOOT banners seen: {len(banners)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
