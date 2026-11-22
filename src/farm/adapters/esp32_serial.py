"""ESP32-S3 serial adapter: protocol v1 over the UART0 USB-serial bridge.

The real transport is pyserial; pyserial is imported lazily so this module can
be tested without the library or hardware. Third-party I/O stays in adapters.
See protocol/serial_v1.md and protocol/serial_vectors.json.
"""
import os
import termios
import time
from collections.abc import Mapping
from typing import Any, Protocol, cast, runtime_checkable

from farm.contracts.actions import Swipe, Tap
from farm.contracts.errors import InputError, UnsupportedAction
from farm.contracts.models import InputMode

_BAUD = 115200
_MIN_SWIPE_MS = 16
_POLL_S = 0.002


@runtime_checkable
class SerialLike(Protocol):
    def write(self, data: bytes) -> int: ...

    def readline(self) -> bytes: ...

    def reset_input_buffer(self) -> None: ...

    def close(self) -> None: ...


def encode_command(command: Mapping[str, Any]) -> str:
    """Encode one structured command as an exact protocol v1 host line."""
    name = command["name"]
    if name == "ping":
        return "PING"
    if name == "res":
        return f"RES {int(command['w'])} {int(command['h'])}"
    if name == "tap":
        parts = ["TAP", str(int(command["x"])), str(int(command["y"]))]
        hold = command.get("hold_ms")
        if hold is not None:
            parts.append(str(int(hold)))
        return " ".join(parts)
    if name == "swipe":
        return "SWIPE " + " ".join(
            str(int(command[key]))
            for key in ("x1", "y1", "x2", "y2", "ms")
        )
    if name == "raw":
        return str(command["line"])
    if name == "boot":
        raise ValueError("BOOT is board-initiated, not a host command")
    raise ValueError(f"unknown command name: {name!r}")


def decode_reply(line: str) -> str | None:
    """Classify one board line: READY, OK, DONE, ERR, BOOT, LOG or OTHER."""
    if not line:
        return None
    if line in ("READY", "OK", "DONE"):
        return line
    if line.startswith("ERR "):
        return "ERR"
    if line.startswith("BOOT "):
        return "BOOT"
    if line.startswith("#"):
        return "LOG"
    return "OTHER"


def _to_pixels(normalized: float, size: int) -> int:
    """Normalized 0..1 to crop pixels 0..size (half-up, clamped)."""
    return max(0, min(size, int(normalized * size + 0.5)))


class Esp32SerialBackend:
    """InputBackend for one seat. One port open per session; strict lockstep."""

    mode = InputMode.HID

    def __init__(
        self,
        serial: SerialLike,
        width: int,
        height: int,
        timeout_s: float = 5.0,
    ) -> None:
        self._serial = serial
        self.width = width
        self.height = height
        self.timeout_s = timeout_s
        self.closed = False
        self.needs_rehandshake = False

    def supports(self, action: object) -> bool:
        return not self.closed and isinstance(action, (Tap, Swipe))

    def perform(self, action: object) -> None:
        if self.closed:
            raise InputError("backend is closed")
        if not self.supports(action):
            raise UnsupportedAction("HID digitizer supports Tap and Swipe only")
        if isinstance(action, Tap):
            command: dict[str, Any] = {
                "name": "tap",
                "x": _to_pixels(action.x, self.width),
                "y": _to_pixels(action.y, self.height),
            }
        elif isinstance(action, Swipe):
            if action.duration_ms < _MIN_SWIPE_MS:
                raise ValueError(f"swipe duration must be >= {_MIN_SWIPE_MS} ms")
            command = {
                "name": "swipe",
                "x1": _to_pixels(action.x1, self.width),
                "y1": _to_pixels(action.y1, self.height),
                "x2": _to_pixels(action.x2, self.width),
                "y2": _to_pixels(action.y2, self.height),
                "ms": action.duration_ms,
            }
        else:
            raise UnsupportedAction("HID digitizer supports Tap and Swipe only")
        self._send_and_expect(encode_command(command), "DONE")

    def handshake(self) -> None:
        """Ping until READY; also covers a board that is still booting.

        Stale input is drained once when the session opens, not here — a
        READY already queued must not be thrown away.
        """
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            self._serial.write(b"PING\n")
            if self._read_until("READY", deadline):
                self.needs_rehandshake = False
                return
        raise InputError("timeout waiting for READY")

    def sync_resolution(self, width: int | None = None, height: int | None = None) -> None:
        w = self.width if width is None else width
        h = self.height if height is None else height
        self._send_and_expect(encode_command({"name": "res", "w": w, "h": h}), "OK")

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self._serial.close()

    def _send_and_expect(self, line: str, expected: str) -> None:
        self._serial.write((line + "\n").encode("ascii"))
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            text = self._next_line()
            if text is None:
                time.sleep(_POLL_S)
                continue
            kind = decode_reply(text)
            if kind == expected:
                return
            if kind == "ERR":
                raise InputError(text[4:])
            if kind == "BOOT":
                self.needs_rehandshake = True
                raise InputError("board reset (BOOT banner received)")
        raise InputError(f"timeout waiting for {expected}")

    def _read_until(self, expected: str, deadline: float) -> bool:
        while time.monotonic() < deadline:
            text = self._next_line()
            if text is None:
                time.sleep(_POLL_S)
                continue
            kind = decode_reply(text)
            if kind == expected:
                return True
            if kind == "BOOT":
                self.needs_rehandshake = True
        return False

    def _next_line(self) -> str | None:
        raw = self._serial.readline()
        if not raw:
            return None
        return raw.decode("utf-8", errors="ignore").strip()


def _preconfigure_port(port: str) -> None:
    """OS-level pre-open: set CLOCAL, clear HUPCL, so the real open cannot
    toggle the auto-reset transistors (architecture §6)."""
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        attrs = termios.tcgetattr(fd)
        attrs[2] |= termios.CLOCAL
        attrs[2] &= ~termios.HUPCL
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    finally:
        os.close(fd)
    time.sleep(0.05)


def _open_pyserial(port: str, baud: int, timeout: float) -> SerialLike:
    import serial  # type: ignore[import-untyped]  # lazy: runtime adapter dependency

    handle = serial.Serial()
    handle.port = port
    handle.baudrate = baud
    handle.timeout = timeout
    handle.dsrdtr = False
    handle.open()
    handle.rts = False  # RTS first, then DTR: never pull EN low
    handle.dtr = False
    # Stale boot logs must be dropped at session open, not in handshake() —
    # a READY already queued by the board must survive.
    handle.reset_input_buffer()
    return cast(SerialLike, handle)


def open_esp32_no_reset(
    port: str, baud: int = _BAUD, timeout: float = 1.0
) -> SerialLike:
    try:
        _preconfigure_port(port)
    except (OSError, termios.error):
        pass  # pre-configure is a mitigation, not a requirement
    return _open_pyserial(port, baud, timeout)
