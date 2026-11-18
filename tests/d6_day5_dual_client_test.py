"""Day-5 dual-client interface test (memo D6, ch. 8).

The same labelled frame corpus drives two clients:
  - the farm's FakeInputBackend (the farm-side contract)
  - a stub of MaaFramework's custom-controller callbacks

If both clients produce equivalent effects from the same corpus, the W5
adopt/reject decision becomes a configuration change instead of a rewrite.
No hardware and no maafw import are needed for this test.
"""
import ast
import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from farm.contracts.actions import Key, Swipe, Tap, Text
from farm.contracts.frame import Frame, FrameSource
from farm.testing.input import FakeInputBackend
from farm.testing.maa_stub import FakeMaaController

CALLBACKS = {
    "connect",
    "screencap",
    "click",
    "swipe",
    "touch_down",
    "touch_move",
    "touch_up",
    "press_key",
    "input_text",
}


def frame(number, width=1080, height=2400, source=FrameSource.UVC):
    return Frame(
        width=width,
        height=height,
        captured_ns=number,
        source=source,
        data=f"frame-{number}".encode(),
    )


CORPUS = (
    (frame(1), Tap(x=0.25, y=0.50)),
    (frame(2), Swipe(x1=0.80, y1=0.70, x2=0.20, y2=0.30, duration_ms=250)),
    (frame(3), Key(code="HOME")),
    (frame(4, source=FrameSource.ADB_SCREENCAP), Text(value="hello")),
)


def drive_maa(controller, action):
    """The trivial Action -> Maa-callback mapping the W6 adapter will own."""
    if isinstance(action, Tap):
        controller.click(action.x, action.y)
    elif isinstance(action, Swipe):
        controller.swipe(
            action.x1, action.y1, action.x2, action.y2, action.duration_ms
        )
    elif isinstance(action, Key):
        controller.press_key(action.code)
    elif isinstance(action, Text):
        controller.input_text(action.value)
    else:
        raise AssertionError(f"unhandled action {action!r}")


def expected_call(action):
    if isinstance(action, Tap):
        return ("click", action.x, action.y)
    if isinstance(action, Swipe):
        return ("swipe", action.x1, action.y1, action.x2, action.y2, action.duration_ms)
    if isinstance(action, Key):
        return ("press_key", action.code)
    return ("input_text", action.value)


# ---- Shape of the stub ------------------------------------------------------


def test_stub_exposes_exactly_the_memo_callback_verbs():
    verbs = {
        name
        for name in dir(FakeMaaController)
        if not name.startswith("_") and callable(getattr(FakeMaaController, name))
    }
    assert verbs == CALLBACKS


def test_stub_does_not_import_maafw():
    """C5: MaaFramework is LGPL-3.0 and must stay outside the farm package."""
    spec = importlib.util.find_spec(FakeMaaController.__module__)
    assert spec is not None and spec.origin is not None
    tree = ast.parse(Path(spec.origin).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(not a.name.startswith("maafw") for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("maafw")


def test_connect_is_recorded():
    controller = FakeMaaController()
    controller.connect()
    assert controller.connected is True
    assert controller.calls == [("connect",)]


def test_screencap_returns_the_corpus_frames_in_order():
    frames = [f for f, _ in CORPUS]
    controller = FakeMaaController(frames)
    assert [controller.screencap() for _ in frames] == frames
    assert controller.screencap() is None
    assert controller.calls == [("screencap",)] * (len(frames) + 1)


def test_touch_verbs_are_available_and_recorded():
    controller = FakeMaaController()
    controller.touch_down(0.1, 0.2)
    controller.touch_move(0.3, 0.4)
    controller.touch_up()
    assert controller.calls == [
        ("touch_down", 0.1, 0.2),
        ("touch_move", 0.3, 0.4),
        ("touch_up",),
    ]


# ---- Equivalence over the whole corpus -------------------------------------


@pytest.mark.parametrize("frame_obj,action", CORPUS, ids=[a.kind for _, a in CORPUS])
def test_action_drives_both_clients_equivalently(frame_obj, action):
    farm_client = FakeInputBackend()
    maa_client = FakeMaaController([frame_obj])

    assert maa_client.screencap() == frame_obj
    farm_client.perform(action)
    drive_maa(maa_client, action)

    assert farm_client.performed == [action]
    assert maa_client.calls == [("screencap",), expected_call(action)]


def test_entire_corpus_produces_matching_logs():
    frames = [f for f, _ in CORPUS]
    actions = [a for _, a in CORPUS]
    farm_client = FakeInputBackend()
    maa_client = FakeMaaController(frames)
    maa_client.connect()

    for frame_obj, action in CORPUS:
        assert maa_client.screencap() == frame_obj
        farm_client.perform(action)
        drive_maa(maa_client, action)

    assert farm_client.performed == actions
    assert maa_client.calls == [("connect",)] + [
        effect
        for frame_obj, action in CORPUS
        for effect in (("screencap",), expected_call(action))
    ]


def test_both_clients_accept_only_normalized_coordinates():
    action = Tap(x=0.0, y=1.0)
    farm_client = FakeInputBackend()
    maa_client = FakeMaaController()
    farm_client.perform(action)
    drive_maa(maa_client, action)
    assert maa_client.calls == [("click", 0.0, 1.0)]

    with pytest.raises(ValidationError):
        Tap(x=1.1, y=0.5)
