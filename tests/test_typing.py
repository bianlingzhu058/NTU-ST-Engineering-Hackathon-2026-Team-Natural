"""Typing emits QWERTY-neighbour typos that get corrected; mouse never touches corners."""
import random
from agent.input.fake_backend import FakeInputBackend
from agent.input.keyboard import HumanTyper
from agent.input.mouse import HumanMouse
from agent.timing import HumanPacer


def _pacer(): return HumanPacer({}, random.Random(1), lambda _: None)


def test_typo_is_corrected():
    backend = FakeInputBackend()
    HumanTyper(backend, _pacer(), random.Random(2), typo_rate=1.0).type_text("a")
    writes = [c for c in backend.calls if c[0] == "write"]
    assert writes[0][1] in "qsz" and writes[-1][1] == "a"
    assert ("press", "backspace") in backend.calls


def test_no_typos_when_rate_zero():
    backend = FakeInputBackend()
    HumanTyper(backend, _pacer(), random.Random(2), typo_rate=0.0).type_text("hello world.")
    assert "".join(c[1] for c in backend.calls if c[0] == "write") == "hello world."


def test_mouse_path_starts_from_current_position_and_avoids_corners():
    backend = FakeInputBackend((1920, 1080))
    mouse = HumanMouse(backend, _pacer(), random.Random(3), steps=10)
    mouse.click(5, 5)  # asks for a corner: must be clamped away from it
    moves = [c[1] for c in backend.calls if c[0] == "move_to"]
    assert all(x >= 40 and y >= 40 for x, y in moves)
    assert abs(moves[0][0] - 960) < 400  # first step is near the starting position, not near (0,0)
