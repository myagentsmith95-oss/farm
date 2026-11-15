"""Reusable contract suites for Matcher, OcrEngine and SettleChecker.

Subclass MatcherContract, OcrContract or SettleContract in a class whose name
starts with Test and implement make_rig(). Real adapters (Maa, OpenCV,
imagehash) must pass the same suites, supplying real frames in their rigs.
"""
from dataclasses import dataclass

import pytest

from farm.contracts.errors import UnknownTemplate
from farm.contracts.frame import Frame, FrameSource
from farm.contracts.matching import (
    Match,
    Matcher,
    OcrEngine,
    Region,
    SettleChecker,
    TextHit,
)

ROI = Region(x=0.25, y=0.25, width=0.5, height=0.5)


def make_frame(data=b"aaaa", width=1080, height=2400, captured_ns=1):
    return Frame(
        width=width,
        height=height,
        captured_ns=captured_ns,
        source=FrameSource.UVC,
        data=data,
    )


@dataclass
class MatcherRig:
    matcher: Matcher
    frame: Frame
    known_template: str


@dataclass
class OcrRig:
    engine: OcrEngine
    frame: Frame


@dataclass
class SettleRig:
    checker: SettleChecker
    frame: Frame
    same: Frame  # same content as frame, different timestamp
    different: Frame  # same size as frame, different content


class MatcherContract:
    def make_rig(self) -> MatcherRig:
        raise NotImplementedError

    @pytest.fixture
    def rig(self):
        return self.make_rig()

    def test_satisfies_protocol(self, rig):
        assert isinstance(rig.matcher, Matcher)

    def test_unknown_template_raises(self, rig):
        with pytest.raises(UnknownTemplate):
            rig.matcher.find(rig.frame, "no-such-template")

    def test_known_template_gives_match_or_none(self, rig):
        result = rig.matcher.find(rig.frame, rig.known_template)
        assert result is None or isinstance(result, Match)

    def test_result_lies_inside_roi(self, rig):
        result = rig.matcher.find(rig.frame, rig.known_template, roi=ROI)
        assert result is None or ROI.contains(result.region)

    @pytest.mark.parametrize("bad", [-0.1, 1.5])
    def test_threshold_out_of_range_raises(self, rig, bad):
        with pytest.raises(ValueError):
            rig.matcher.find(rig.frame, rig.known_template, threshold=bad)


class OcrContract:
    def make_rig(self) -> OcrRig:
        raise NotImplementedError

    @pytest.fixture
    def rig(self):
        return self.make_rig()

    def test_satisfies_protocol(self, rig):
        assert isinstance(rig.engine, OcrEngine)

    def test_read_returns_a_list_of_hits(self, rig):
        hits = rig.engine.read(rig.frame)
        assert isinstance(hits, list)
        assert all(isinstance(hit, TextHit) for hit in hits)

    def test_hits_lie_inside_roi(self, rig):
        for hit in rig.engine.read(rig.frame, roi=ROI):
            assert ROI.contains(hit.region)


class SettleContract:
    def make_rig(self) -> SettleRig:
        raise NotImplementedError

    @pytest.fixture
    def rig(self):
        return self.make_rig()

    def test_satisfies_protocol(self, rig):
        assert isinstance(rig.checker, SettleChecker)

    @pytest.mark.parametrize("tolerance", [0.0, 0.05, 1.0])
    def test_identical_content_is_settled(self, rig, tolerance):
        assert rig.checker.settled(rig.frame, rig.same, tolerance=tolerance)

    def test_result_is_symmetric(self, rig):
        forward = rig.checker.settled(rig.frame, rig.different, tolerance=0.05)
        backward = rig.checker.settled(rig.different, rig.frame, tolerance=0.05)
        assert forward == backward

    def test_different_content_is_not_settled_at_zero_tolerance(self, rig):
        assert not rig.checker.settled(rig.frame, rig.different, tolerance=0.0)

    @pytest.mark.parametrize("bad", [-0.1, 1.1])
    def test_tolerance_out_of_range_raises(self, rig, bad):
        with pytest.raises(ValueError):
            rig.checker.settled(rig.frame, rig.same, tolerance=bad)

    def test_full_tolerance_settles_same_size_frames(self, rig):
        assert rig.checker.settled(rig.frame, rig.different, tolerance=1.0)
