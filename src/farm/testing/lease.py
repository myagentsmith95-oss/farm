"""In-memory LeaseManager with an injected clock."""
import time
from collections.abc import Callable

from farm.contracts.errors import LeaseExpired, LeaseHeld
from farm.contracts.lease import Lease

_NS_PER_MS = 1_000_000


def _check_ttl(ttl_ms: int) -> None:
    if ttl_ms <= 0:
        raise ValueError(f"ttl_ms must be positive, got {ttl_ms}")


class FakeLeaseManager:
    def __init__(self, clock_ns: Callable[[], int] = time.monotonic_ns) -> None:
        self._clock_ns = clock_ns
        self._current: dict[str, Lease] = {}
        self._last_token: dict[str, int] = {}

    def _live(self, device_id: str) -> Lease | None:
        lease = self._current.get(device_id)
        if lease is not None and self._clock_ns() < lease.expires_ns:
            return lease
        return None

    def acquire(self, device_id: str, holder: str, ttl_ms: int) -> Lease:
        _check_ttl(ttl_ms)
        if self._live(device_id) is not None:
            raise LeaseHeld(device_id)
        token = self._last_token.get(device_id, 0) + 1
        lease = Lease(
            device_id=device_id,
            holder=holder,
            token=token,
            expires_ns=self._clock_ns() + ttl_ms * _NS_PER_MS,
        )
        self._last_token[device_id] = token
        self._current[device_id] = lease
        return lease

    def renew(self, lease: Lease, ttl_ms: int) -> Lease:
        _check_ttl(ttl_ms)
        if not self.is_valid(lease):
            raise LeaseExpired(lease.device_id)
        renewed = lease.model_copy(
            update={"expires_ns": self._clock_ns() + ttl_ms * _NS_PER_MS}
        )
        self._current[lease.device_id] = renewed
        return renewed

    def release(self, lease: Lease) -> None:
        current = self._current.get(lease.device_id)
        if current is not None and current.token == lease.token:
            del self._current[lease.device_id]

    def is_valid(self, lease: Lease) -> bool:
        live = self._live(lease.device_id)
        return (
            live is not None
            and live.token == lease.token
            and live.holder == lease.holder
        )
