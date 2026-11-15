from matching_suite import (
    MatcherContract,
    MatcherRig,
    OcrContract,
    OcrRig,
    SettleContract,
    SettleRig,
    make_frame,
)

from farm.contracts.matching import Match, Region, TextHit
from farm.testing.matching import FakeMatcher, FakeOcrEngine, FakeSettleChecker

BUTTON = Region(x=0.3, y=0.3, width=0.2, height=0.2)
FAR = Region(x=0.6, y=0.6, width=0.3, height=0.3)
LOGIN = Match(region=BUTTON, score=0.9)
HELLO = TextHit(text="hello", region=BUTTON, confidence=0.95)


class TestFakeMatcher(MatcherContract):
    def make_rig(self):
        return MatcherRig(
            matcher=FakeMatcher({"login": LOGIN}),
            frame=make_frame(),
            known_template="login",
        )


class TestFakeOcrEngine(OcrContract):
    def make_rig(self):
        return OcrRig(engine=FakeOcrEngine([HELLO]), frame=make_frame())


class TestFakeSettleChecker(SettleContract):
    def make_rig(self):
        return SettleRig(
            checker=FakeSettleChecker(),
            frame=make_frame(),
            same=make_frame(captured_ns=2),
            different=make_frame(data=b"bbbb"),
        )


def test_matcher_below_threshold_returns_none():
    matcher = FakeMatcher({"login": LOGIN})
    assert matcher.find(make_frame(), "login", threshold=0.95) is None


def test_matcher_roi_excluding_the_match_returns_none():
    matcher = FakeMatcher({"login": LOGIN})
    assert matcher.find(make_frame(), "login", roi=FAR) is None


def test_matcher_known_but_absent_template_returns_none():
    matcher = FakeMatcher({"login": None})
    assert matcher.find(make_frame(), "login") is None


def test_ocr_roi_filters_hits():
    engine = FakeOcrEngine([HELLO])
    assert engine.read(make_frame(), roi=FAR) == []
    assert engine.read(make_frame()) == [HELLO]


def test_settle_respects_tolerance():
    checker = FakeSettleChecker()
    before = make_frame(data=b"aaaaaaaaaa")
    after = make_frame(data=b"aaaaaaaaab")
    assert checker.settled(before, after, tolerance=0.1)
    assert not checker.settled(before, after, tolerance=0.05)


def test_settle_frames_of_different_size_are_never_settled():
    small = make_frame(width=720, height=1600)
    assert not FakeSettleChecker().settled(make_frame(), small, tolerance=1.0)
