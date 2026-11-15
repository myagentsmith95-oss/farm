"""A manually advanced monotonic clock for freshness tests."""


class FakeClock:
    def __init__(self, start_ns: int = 10_000_000_000) -> None:
        self._now_ns = start_ns

    def now_ns(self) -> int:
        return self._now_ns

    def advance_ms(self, ms: int) -> None:
        self._now_ns += ms * 1_000_000
