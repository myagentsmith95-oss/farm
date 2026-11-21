from farm.contracts.actions import Swipe, Tap
from farm.contracts.models import InputMode
from farm.testing.input import FakeInputBackend
from tests.contracts.input_backend_suite import SAMPLE_ACTIONS, InputBackendContract


class TestFakeInputBackendFull(InputBackendContract):
    def make_backend(self):
        return FakeInputBackend()


class TestFakeInputBackendTapOnly(InputBackendContract):
    def make_backend(self):
        return FakeInputBackend(mode=InputMode.ADB, supported_kinds=["tap"])


def test_fake_records_performed_actions_in_order():
    backend = FakeInputBackend()
    for action in SAMPLE_ACTIONS:
        backend.perform(action)
    assert backend.performed == SAMPLE_ACTIONS


def test_tap_only_fake_really_rejects_swipe():
    # Guards the suite against passing vacuously: the unsupported path must exist.
    backend = FakeInputBackend(supported_kinds=["tap"])
    assert backend.supports(Tap(x=0.5, y=0.5))
    assert not backend.supports(Swipe(x1=0.1, y1=0.1, x2=0.9, y2=0.9, duration_ms=100))
