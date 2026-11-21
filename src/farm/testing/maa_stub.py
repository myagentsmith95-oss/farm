"""Stub of MaaFramework's custom-controller callback shape.

MaaFramework is LGPL-3.0 and lives in its own distribution (memo C5). This
fake imports nothing from maafw: it only mirrors the verbs the custom
controller exposes, so the week-one dual-client test can prove that the
farm's seams and Maa's controller are interchangeable.

Coordinates are normalized (0..1) here, as in farm.contracts.actions. The
real week-six adapter owns the conversion to device pixels, like every
other backend. press_key here records the canonical KeyCode string; real Maa
takes an integer keycode, so the W6 adapter owns that mapping too.
"""
from collections.abc import Iterable

from farm.contracts.frame import Frame


class FakeMaaController:
    """Records the callbacks a Maa-style controller would receive."""

    def __init__(self, frames: Iterable[Frame] = ()) -> None:
        self._frames = iter(frames)
        self.calls: list[tuple[object, ...]] = []
        self.connected = False

    def connect(self) -> None:
        self.connected = True
        self.calls.append(("connect",))

    def screencap(self) -> Frame | None:
        self.calls.append(("screencap",))
        return next(self._frames, None)

    def click(self, x: float, y: float) -> None:
        self.calls.append(("click", x, y))

    def swipe(
        self, x1: float, y1: float, x2: float, y2: float, duration_ms: int
    ) -> None:
        self.calls.append(("swipe", x1, y1, x2, y2, duration_ms))

    def touch_down(self, x: float, y: float) -> None:
        self.calls.append(("touch_down", x, y))

    def touch_move(self, x: float, y: float) -> None:
        self.calls.append(("touch_move", x, y))

    def touch_up(self) -> None:
        self.calls.append(("touch_up",))

    def press_key(self, key: str) -> None:
        self.calls.append(("press_key", key))

    def input_text(self, text: str) -> None:
        self.calls.append(("input_text", text))
