"""Check fake typing emits a correction when typo probability is certain."""
import random
from agent.input.fake_backend import FakeInputBackend
from agent.input.keyboard import HumanTyper
from agent.timing import HumanPacer


def test_typo_is_corrected():
    backend = FakeInputBackend()
    pacer = HumanPacer({"micro_seconds": [0, 0], "step_seconds": [0, 0]}, random.Random(1), lambda _: None)
    HumanTyper(backend, pacer, random.Random(2), 1).type_text("a")
    assert backend.calls == [("write", "x"), ("press", "backspace"), ("write", "a")]
