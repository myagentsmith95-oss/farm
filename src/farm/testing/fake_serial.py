"""In-memory serial transport for adapter tests. No pyserial or hardware needed."""
from collections import deque


class FakeEsp32Serial:
    """The small subset of pyserial that the ESP32 adapter uses."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self._inbound: deque[bytes] = deque()
        self.closed = False

    def feed(self, line: str) -> None:
        """Queue one board-initiated line."""
        self._inbound.append((line + "\n").encode())

    def write(self, data: bytes) -> int:
        if self.closed:
            raise OSError("serial port is closed")
        self.sent.append(data)
        return len(data)

    def readline(self) -> bytes:
        if self.closed or not self._inbound:
            return b""
        return self._inbound.popleft()

    def reset_input_buffer(self) -> None:
        self._inbound.clear()

    def close(self) -> None:
        self.closed = True
