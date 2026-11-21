"""Vision seams. PROVISIONAL: revisit at the W5 MaaFramework gate.

Matcher and OcrEngine are what Maa or OpenCV implement. SettleChecker is a
separate seam because it is backed by imagehash in both cases and runs before
every action, so it must stay in-process and cheap. All coordinates are
normalized (0 to 1) like Action, so Match.center can feed a Tap directly.
"""
from typing import Annotated, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from farm.contracts.frame import Frame

_EPS = 1e-9

Unit = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
Size = Annotated[float, Field(gt=0.0, le=1.0, allow_inf_nan=False)]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Region(_Model):
    """A rectangle on the screen. (x, y) is the top-left corner."""

    x: Unit
    y: Unit
    width: Size
    height: Size

    @model_validator(mode="after")
    def _inside_screen(self) -> "Region":
        if self.x + self.width > 1.0 + _EPS or self.y + self.height > 1.0 + _EPS:
            raise ValueError("region extends past the screen edge")
        return self

    @property
    def center(self) -> tuple[float, float]:
        return (
            min(1.0, self.x + self.width / 2),
            min(1.0, self.y + self.height / 2),
        )

    def contains(self, other: "Region") -> bool:
        return (
            other.x >= self.x - _EPS
            and other.y >= self.y - _EPS
            and other.x + other.width <= self.x + self.width + _EPS
            and other.y + other.height <= self.y + self.height + _EPS
        )


class Match(_Model):
    region: Region
    score: Unit

    @property
    def center(self) -> tuple[float, float]:
        return self.region.center


class TextHit(_Model):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    region: Region
    confidence: Unit


@runtime_checkable
class Matcher(Protocol):
    def find(
        self,
        frame: Frame,
        template: str,
        *,
        roi: Region | None = None,
        threshold: float = 0.8,
    ) -> Match | None:
        """Best match of a named template, or None if nothing reaches threshold.
        A returned match lies inside roi when one is given. Raises
        UnknownTemplate for an unregistered name, ValueError if threshold is
        outside 0 to 1."""
        ...


@runtime_checkable
class OcrEngine(Protocol):
    def read(self, frame: Frame, *, roi: Region | None = None) -> list[TextHit]:
        """Text found in the frame; every hit lies inside roi when one is given."""
        ...


@runtime_checkable
class SettleChecker(Protocol):
    def settled(
        self, previous: Frame, current: Frame, *, tolerance: float = 0.05
    ) -> bool:
        """True if the screen stopped changing between the two frames. Symmetric.
        Raises ValueError if tolerance is outside 0 to 1."""
        ...
