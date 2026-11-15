"""In-memory InputBackend that records what it was asked to do."""
from collections.abc import Iterable

from farm.contracts.actions import Action
from farm.contracts.errors import InputError, UnsupportedAction
from farm.contracts.models import InputMode

ALL_KINDS = ("tap", "swipe", "key", "text")


class FakeInputBackend:
    def __init__(
        self,
        mode: InputMode = InputMode.HID,
        supported_kinds: Iterable[str] = ALL_KINDS,
    ) -> None:
        self.mode = mode
        self._supported = frozenset(supported_kinds)
        self.performed: list[Action] = []
        self.closed = False

    def supports(self, action: Action) -> bool:
        return action.kind in self._supported

    def perform(self, action: Action) -> None:
        if self.closed:
            raise InputError("backend is closed")
        if not self.supports(action):
            raise UnsupportedAction(f"{action.kind} not supported by {self.mode}")
        self.performed.append(action)

    def close(self) -> None:
        self.closed = True
