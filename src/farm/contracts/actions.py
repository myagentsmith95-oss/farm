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
    """Canonical key names shared by scenarios and both seat classes (D-7).

    HOME/BACK map to consumer usages 0x223/0x224 in composite firmware;
    ENTER/DEL map to keyboard usages 0x28/0x2A. APP_SWITCH has no HID usage
    and is performed as a touch macro or ADB keycode 187, so the HID backend
    reports supports() == False for it. Power and volume controls are out of
    scope by decision D-4.
    """

    HOME = "HOME"
    BACK = "BACK"
    ENTER = "ENTER"
    DEL = "DEL"
    APP_SWITCH = "APP_SWITCH"


class Key(_Action):
    kind: Literal["key"] = "key"
    code: KeyCode


class Text(_Action):
    kind: Literal["text"] = "text"
    value: Annotated[str, Field(min_length=1)]


Action = Annotated[Tap | Swipe | Key | Text, Field(discriminator="kind")]
