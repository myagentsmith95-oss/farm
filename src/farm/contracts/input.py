"""InputBackend seam. PROVISIONAL: revisit after the W2 ESP32 hardware test.

One backend per device and mode. Backends never see leases: the InputRouter
checks the lease before calling perform(). Actions use normalized coordinates;
each backend converts to its own units. Key actions carry a canonical KeyCode;
each adapter maps it to its own key language (HID usage IDs, Android keycodes)
and raises UnsupportedAction for keys it cannot map.
"""
from typing import Protocol, runtime_checkable

from farm.contracts.actions import Action
from farm.contracts.models import InputMode


@runtime_checkable
class InputBackend(Protocol):
    mode: InputMode

    def supports(self, action: Action) -> bool:
        """True if perform() can carry out this kind of action."""
        ...

    def perform(self, action: Action) -> None:
        """Carry out the action. Blocks until it is fully injected; for Swipe,
        until the gesture completes. A backend that cannot block must document
        its own completion semantics. Raises InputError if closed or injection
        fails, UnsupportedAction if supports(action) is False or a canonical
        key cannot be mapped."""
        ...

    def close(self) -> None:
        """Release the backend. Safe to call more than once."""
        ...
