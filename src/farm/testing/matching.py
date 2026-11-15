"""In-memory Matcher, OcrEngine and SettleChecker for hardware-free tests."""
from collections.abc import Iterable, Mapping

from farm.contracts.errors import UnknownTemplate
from farm.contracts.frame import Frame
from farm.contracts.matching import Match, Region, TextHit


def _check_unit(value: float, name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1, got {value}")


class FakeMatcher:
    """templates maps a name to the Match it yields, or None if known but absent."""

    def __init__(self, templates: Mapping[str, Match | None] | None = None) -> None:
        self._templates = dict(templates or {})

    def find(
        self,
        frame: Frame,
        template: str,
        *,
        roi: Region | None = None,
        threshold: float = 0.8,
    ) -> Match | None:
        _check_unit(threshold, "threshold")
        if template not in self._templates:
            raise UnknownTemplate(template)
        match = self._templates[template]
        if match is None or match.score < threshold:
            return None
        if roi is not None and not roi.contains(match.region):
            return None
        return match


class FakeOcrEngine:
    def __init__(self, hits: Iterable[TextHit] = ()) -> None:
        self._hits = list(hits)

    def read(self, frame: Frame, *, roi: Region | None = None) -> list[TextHit]:
        return [h for h in self._hits if roi is None or roi.contains(h.region)]


class FakeSettleChecker:
    """Compares encoded bytes: the fraction of differing bytes must be within
    tolerance. Frames of different size are never settled."""

    def settled(
        self, previous: Frame, current: Frame, *, tolerance: float = 0.05
    ) -> bool:
        _check_unit(tolerance, "tolerance")
        if (previous.width, previous.height) != (current.width, current.height):
            return False
        a, b = previous.data, current.data
        differing = sum(x != y for x, y in zip(a, b)) + abs(len(a) - len(b))
        return differing / max(len(a), len(b)) <= tolerance
