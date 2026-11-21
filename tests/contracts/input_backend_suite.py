"""Reusable contract suite for InputBackend implementations.

Subclass InputBackendContract in a class whose name starts with Test, and
implement make_backend(). Real adapters (ESP32 HID, ADB) must pass this too.
Rules: a closed backend raises InputError for every action; an action the
backend does not support raises UnsupportedAction; close() is idempotent.
"""
import pytest

from farm.contracts.actions import Key, Swipe, Tap, Text
from farm.contracts.errors import InputError, UnsupportedAction
from farm.contracts.input import InputBackend
from farm.contracts.models import InputMode

SAMPLE_ACTIONS = [
    Tap(x=0.5, y=0.5),
    Swipe(x1=0.1, y1=0.2, x2=0.8, y2=0.9, duration_ms=250),
    Key(code="HOME"),
    Text(value="hello"),
]


class InputBackendContract:
    def make_backend(self) -> InputBackend:
        raise NotImplementedError

    @pytest.fixture
    def backend(self):
        instance = self.make_backend()
        yield instance
        instance.close()

    def test_satisfies_protocol(self, backend):
        assert isinstance(backend, InputBackend)
        assert isinstance(backend.mode, InputMode)

    def test_perform_docstring_pins_completion_semantics(self, backend):
        # N4: a queued swipe and a finished swipe are different budgets.
        doc = InputBackend.perform.__doc__ or ""
        assert "fully injected" in doc
        assert "gesture completes" in doc

    @pytest.mark.parametrize("action", SAMPLE_ACTIONS, ids=lambda a: a.kind)
    def test_supports_matches_perform(self, backend, action):
        if backend.supports(action):
            backend.perform(action)
        else:
            with pytest.raises(UnsupportedAction):
                backend.perform(action)

    def test_perform_after_close_raises_input_error(self, backend):
        backend.close()
        for action in SAMPLE_ACTIONS:
            with pytest.raises(InputError):
                backend.perform(action)

    def test_close_is_idempotent(self, backend):
        backend.close()
        backend.close()
