"""Run-control coverage is kept with runtime changes because action-boundary
pause and stop behavior must remain reliable for desktop runs.
"""
import threading
import time
import random

import pytest

from agent.input.fake_backend import FakeInputBackend
from agent.input.keyboard import HumanTyper
from agent.run_control import RunControl, RunStopped
from agent.timing import HumanPacer


def test_checkpoint_waits_while_paused_and_resumes():
    control = RunControl()
    control.pause()
    reached = threading.Event()

    def checkpoint():
        control.checkpoint()
        reached.set()

    worker = threading.Thread(target=checkpoint)
    worker.start()
    time.sleep(0.03)
    assert not reached.is_set()
    control.resume()
    worker.join(timeout=1)
    assert reached.is_set()


def test_stop_releases_pause_and_interrupts_checkpoint():
    control = RunControl()
    control.pause()
    result = []

    def checkpoint():
        try:
            control.checkpoint()
        except RunStopped:
            result.append("stopped")

    worker = threading.Thread(target=checkpoint)
    worker.start()
    time.sleep(0.03)
    control.stop()
    worker.join(timeout=1)
    assert result == ["stopped"]


def test_stop_file_interrupts_checkpoint():
    state = {"stop": False}
    control = RunControl(lambda: state["stop"])
    state["stop"] = True
    with pytest.raises(RunStopped):
        control.checkpoint()


def test_typing_stops_at_the_next_character_boundary():
    control = RunControl()

    class StopAfterFirstWrite(FakeInputBackend):
        def write(self, text):
            super().write(text)
            control.stop()

    backend = StopAfterFirstWrite()
    pacer = HumanPacer({"micro_seconds": [0, 0], "step_seconds": [0, 0]},
                       random.Random(1), lambda _: None, control)
    typer = HumanTyper(backend, pacer, random.Random(2), 0, control)
    with pytest.raises(RunStopped):
        typer.type_text("ab")
    assert backend.calls == [("write", "a")]
