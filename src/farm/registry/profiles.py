"""Device profile store: the registry's inventory of enrolled phones."""
from collections.abc import Iterable

from farm.contracts.errors import FarmError
from farm.contracts.models import DeviceProfile


class ProfileAlreadyEnrolled(FarmError):
    """A profile with this device id is already in the store."""


class ProfileNotFound(FarmError):
    """No profile with this device id is enrolled."""


class ProfileStore:
    """In-memory enrollment of device profiles, keyed by device id."""

    def __init__(self, profiles: Iterable[DeviceProfile] = ()) -> None:
        self._profiles: dict[str, DeviceProfile] = {}
        for profile in profiles:
            self.add(profile)

    def add(self, profile: DeviceProfile) -> None:
        if profile.device_id in self._profiles:
            raise ProfileAlreadyEnrolled(profile.device_id)
        self._profiles[profile.device_id] = profile

    def get(self, device_id: str) -> DeviceProfile:
        try:
            return self._profiles[device_id]
        except KeyError:
            raise ProfileNotFound(device_id) from None

    def remove(self, device_id: str) -> None:
        try:
            del self._profiles[device_id]
        except KeyError:
            raise ProfileNotFound(device_id) from None

    def all(self) -> tuple[DeviceProfile, ...]:
        return tuple(self._profiles.values())
