"""Device profile store: the registry's inventory of enrolled phones."""
import pytest

from farm.contracts.models import DeviceProfile, InputMode
from farm.registry import ProfileAlreadyEnrolled, ProfileNotFound, ProfileStore


def profile(device_id="seat-01"):
    return DeviceProfile(device_id=device_id, input_modes=[InputMode.HID])


def test_empty_store_has_no_profiles():
    assert ProfileStore().all() == ()


def test_add_then_get():
    store = ProfileStore()
    p = profile()
    store.add(p)
    assert store.get("seat-01") == p


def test_initial_iterable_is_loaded_in_order():
    first, second = profile("seat-01"), profile("seat-02")
    store = ProfileStore([first, second])
    assert store.all() == (first, second)


def test_duplicate_device_id_is_rejected():
    store = ProfileStore([profile()])
    with pytest.raises(ProfileAlreadyEnrolled):
        store.add(profile())


def test_duplicate_in_initial_iterable_is_rejected():
    with pytest.raises(ProfileAlreadyEnrolled):
        ProfileStore([profile(), profile()])


def test_get_missing_raises_profile_not_found():
    with pytest.raises(ProfileNotFound):
        ProfileStore().get("seat-99")


def test_remove_deletes_the_profile():
    store = ProfileStore([profile()])
    store.remove("seat-01")
    assert store.all() == ()
    with pytest.raises(ProfileNotFound):
        store.get("seat-01")


def test_remove_missing_raises_profile_not_found():
    with pytest.raises(ProfileNotFound):
        ProfileStore().remove("seat-99")


def test_all_returns_an_immutable_snapshot():
    store = ProfileStore([profile()])
    snapshot = store.all()
    store.add(profile("seat-02"))
    assert snapshot == (profile(),)
    assert isinstance(snapshot, tuple)


def test_errors_are_farm_errors():
    from farm.contracts.errors import FarmError

    assert issubclass(ProfileAlreadyEnrolled, FarmError)
    assert issubclass(ProfileNotFound, FarmError)
