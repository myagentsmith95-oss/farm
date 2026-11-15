"""LeaseManager seam. PROVISIONAL: revisit when the supervisor is written.

Implemented by the runner's supervisor (single writer). The InputRouter checks
is_valid() before every perform(); backends never see leases. The token is a
fencing token: it increases on every grant for a device and is unchanged by
renew(), so a late write from an expired holder can be recognised.
"""
from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Lease(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    device_id: NonBlank
    holder: NonBlank
    token: Annotated[int, Field(ge=1)]
    expires_ns: Annotated[int, Field(ge=0)]  # monotonic clock, ns


@runtime_checkable
class LeaseManager(Protocol):
    def acquire(self, device_id: str, holder: str, ttl_ms: int) -> Lease:
        """Lease a device. Raises LeaseHeld if an unexpired lease exists (even
        for the same holder), ValueError if ttl_ms <= 0."""
        ...

    def renew(self, lease: Lease, ttl_ms: int) -> Lease:
        """Extend a still-valid lease from now. Raises LeaseExpired if it
        expired, was released or was taken over, ValueError if ttl_ms <= 0."""
        ...

    def release(self, lease: Lease) -> None:
        """Give the device back. Idempotent; a stale lease is ignored."""
        ...

    def is_valid(self, lease: Lease) -> bool:
        """True while this exact grant is current and now < expires_ns."""
        ...
