"""Reusable contract suite for LeaseManager implementations.

Subclass LeaseManagerContract in a class whose name starts with Test and
implement make_rig(). An implementation must read time from the injected clock.
Rules:
- one holder per device at a time: acquire on a held device raises LeaseHeld,
  even for the same holder; devices are independent
- a lease is valid while now < expires_ns, so it is expired exactly at its TTL
- the fencing token increases on every grant for a device and is unchanged by
  renew
- renew raises LeaseExpired for an expired, released or taken-over lease
- release is idempotent, and a stale release never frees a newer holder's lease
- a non-positive ttl raises ValueError
"""
from dataclasses import dataclass

import pytest

from farm.contracts.errors import LeaseExpired, LeaseHeld
from farm.contracts.lease import LeaseManager
from farm.testing.clock import FakeClock

MS = 1_000_000


@dataclass
class LeaseRig:
    manager: LeaseManager
    clock: FakeClock


class LeaseManagerContract:
    def make_rig(self) -> LeaseRig:
        raise NotImplementedError

    @pytest.fixture
    def rig(self):
        return self.make_rig()

    def test_satisfies_protocol(self, rig):
        assert isinstance(rig.manager, LeaseManager)

    def test_acquire_returns_lease_for_the_caller(self, rig):
        lease = rig.manager.acquire("seat-01", "runner-a", 1000)
        assert lease.device_id == "seat-01"
        assert lease.holder == "runner-a"
        assert lease.expires_ns == rig.clock.now_ns() + 1000 * MS
        assert rig.manager.is_valid(lease)

    def test_second_acquire_on_held_device_raises(self, rig):
        rig.manager.acquire("seat-01", "runner-a", 1000)
        with pytest.raises(LeaseHeld):
            rig.manager.acquire("seat-01", "runner-b", 1000)

    def test_same_holder_cannot_acquire_twice(self, rig):
        rig.manager.acquire("seat-01", "runner-a", 1000)
        with pytest.raises(LeaseHeld):
            rig.manager.acquire("seat-01", "runner-a", 1000)

    def test_different_devices_are_independent(self, rig):
        first = rig.manager.acquire("seat-01", "runner-a", 1000)
        second = rig.manager.acquire("seat-02", "runner-a", 1000)
        assert rig.manager.is_valid(first) and rig.manager.is_valid(second)

    def test_release_frees_the_device(self, rig):
        lease = rig.manager.acquire("seat-01", "runner-a", 1000)
        rig.manager.release(lease)
        again = rig.manager.acquire("seat-01", "runner-b", 1000)
        assert rig.manager.is_valid(again)

    def test_tokens_increase_across_grants(self, rig):
        first = rig.manager.acquire("seat-01", "runner-a", 1000)
        rig.manager.release(first)
        second = rig.manager.acquire("seat-01", "runner-b", 1000)
        assert second.token > first.token

    def test_expired_lease_can_be_taken_over(self, rig):
        old = rig.manager.acquire("seat-01", "runner-a", 1000)
        rig.clock.advance_ms(1000)
        new = rig.manager.acquire("seat-01", "runner-b", 1000)
        assert not rig.manager.is_valid(old)
        assert rig.manager.is_valid(new)
        assert new.token > old.token

    def test_lease_is_valid_until_exactly_its_ttl(self, rig):
        lease = rig.manager.acquire("seat-01", "runner-a", 1000)
        rig.clock.advance_ms(999)
        assert rig.manager.is_valid(lease)
        rig.clock.advance_ms(1)
        assert not rig.manager.is_valid(lease)

    def test_renew_extends_expiry_from_now(self, rig):
        lease = rig.manager.acquire("seat-01", "runner-a", 1000)
        rig.clock.advance_ms(500)
        renewed = rig.manager.renew(lease, 1000)
        assert renewed.expires_ns == rig.clock.now_ns() + 1000 * MS
        rig.clock.advance_ms(700)
        assert rig.manager.is_valid(renewed)

    def test_renew_keeps_the_token(self, rig):
        lease = rig.manager.acquire("seat-01", "runner-a", 1000)
        assert rig.manager.renew(lease, 1000).token == lease.token

    def test_is_valid_checks_the_current_grant_after_renew(self, rig):
        # CR-4: validity belongs to the grant, not to the snapshot's own
        # expires_ns. An old snapshot stays valid while the renewed grant is.
        old = rig.manager.acquire("seat-01", "runner-a", 100)
        rig.manager.renew(old, 1000)
        rig.clock.advance_ms(500)
        assert old.expires_ns < rig.clock.now_ns()
        assert rig.manager.is_valid(old)

    def test_is_valid_docstring_pins_current_grant_semantics(self, rig):
        doc = LeaseManager.is_valid.__doc__ or ""
        assert "current grant" in doc and "renew" in doc

    def test_renew_expired_lease_raises(self, rig):
        lease = rig.manager.acquire("seat-01", "runner-a", 1000)
        rig.clock.advance_ms(1000)
        with pytest.raises(LeaseExpired):
            rig.manager.renew(lease, 1000)

    def test_renew_after_takeover_raises(self, rig):
        old = rig.manager.acquire("seat-01", "runner-a", 1000)
        rig.clock.advance_ms(1000)
        rig.manager.acquire("seat-01", "runner-b", 1000)
        with pytest.raises(LeaseExpired):
            rig.manager.renew(old, 1000)

    def test_release_is_idempotent(self, rig):
        lease = rig.manager.acquire("seat-01", "runner-a", 1000)
        rig.manager.release(lease)
        rig.manager.release(lease)

    def test_stale_release_does_not_free_the_new_holder(self, rig):
        old = rig.manager.acquire("seat-01", "runner-a", 1000)
        rig.clock.advance_ms(1000)
        new = rig.manager.acquire("seat-01", "runner-b", 1000)
        rig.manager.release(old)
        assert rig.manager.is_valid(new)

    def test_released_lease_is_invalid(self, rig):
        lease = rig.manager.acquire("seat-01", "runner-a", 1000)
        rig.manager.release(lease)
        assert not rig.manager.is_valid(lease)

    def test_renew_released_lease_raises(self, rig):
        lease = rig.manager.acquire("seat-01", "runner-a", 1000)
        rig.manager.release(lease)
        with pytest.raises(LeaseExpired):
            rig.manager.renew(lease, 1000)

    @pytest.mark.parametrize("ttl", [0, -5])
    def test_acquire_rejects_non_positive_ttl(self, rig, ttl):
        with pytest.raises(ValueError):
            rig.manager.acquire("seat-01", "runner-a", ttl)

    @pytest.mark.parametrize("ttl", [0, -5])
    def test_renew_rejects_non_positive_ttl(self, rig, ttl):
        lease = rig.manager.acquire("seat-01", "runner-a", 1000)
        with pytest.raises(ValueError):
            rig.manager.renew(lease, ttl)
