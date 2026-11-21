"""Actions: a pure description of what to do, in normalized coordinates.

(0, 0) is the top-left of the screen and (1, 1) the bottom-right. Each
InputBackend converts to its own units. An action carries no device id: the
target is the per-device backend it is handed to.
"""
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Coord = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]


class _Action(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Tap(_Action):
    kind: Literal["tap"] = "tap"
    x: Coord
    y: Coord


class Swipe(_Action):
    kind: Literal["swipe"] = "swipe"
    x1: Coord
    y1: Coord
    x2: Coord
    y2: Coord
    duration_ms: Annotated[int, Field(gt=0)]


class KeyCode(StrEnum):
    """Canonical key names. Adapters map these to HID usage IDs or Android
    keycodes; scenarios and the dual-client corpus stay backend-independent."""

    HOME = "HOME"
    BACK = "BACK"
    APP_SWITCH = "APP_SWITCH"
    ENTER = "ENTER"
    DEL = "DEL"
    POWER = "POWER"
    VOLUME_UP = "VOLUME_UP"
    VOLUME_DOWN = "VOLUME_DOWN"


class Key(_Action):
    kind: Literal["key"] = "key"
    code: KeyCode


class Text(_Action):
    kind: Literal["text"] = "text"
    value: Annotated[str, Field(min_length=1)]


Action = Annotated[Tap | Swipe | Key | Text, Field(discriminator="kind")]
