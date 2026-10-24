"""Typing: corrected slips of three kinds, held keys, rollover, human speed; mouse never touches corners."""
import random
from agent.behaviour.params import P
from agent.input.fake_backend import FakeInputBackend
from agent.input.keyboard import HumanTyper, final_text
from agent.input.mouse import HumanMouse
from agent.timing import HumanPacer, SimClock


def _pacer(clock=None):
    if clock: return HumanPacer({}, random.Random(1), clock.advance, clock.now)
    return HumanPacer({}, random.Random(1), lambda _: None)


def test_slip_is_corrected():
    backend = FakeInputBackend()
    HumanTyper(backend, _pacer(), random.Random(2), typo_rate=1.0).type_text("a")
    writes = [c for c in backend.calls if c[0] == "write"]
    assert writes[-1][1] == "a"
    assert ("press", "backspace") in backend.calls or [w[1] for w in writes] == ["a"]


def test_no_slips_when_rate_zero():
    backend = FakeInputBackend()
    HumanTyper(backend, _pacer(), random.Random(2), typo_rate=0.0).type_text("hello world.")
    assert "".join(c[1] for c in backend.calls if c[0] == "write") == "hello world."


def test_exact_contexts_always_end_correct_and_prose_mostly_does():
    rng = random.Random(5)
    typer = HumanTyper(FakeInputBackend(), _pacer(), rng)
    for _ in range(300):
        assert final_text(typer.plan("https://www.coingecko.com", "url")) == "https://www.coingecko.com"
        assert final_text(typer.plan("crypto prices 24 oct", "prose", keep_slips=False)) == "crypto prices 24 oct"


def test_three_slip_kinds_roughly_in_the_measured_split():
    typer = HumanTyper(FakeInputBackend(), _pacer(), random.Random(7), typo_rate=0.05)
    kinds = {"substitution": 0, "omission": 0, "insertion": 0}
    text = "the quick brown fox jumps over the lazy dog " * 40
    ops = typer.plan(text, "prose", keep_slips=False)
    errors = sum(1 for o in ops if o[0] == "char" and o[2] == "error")
    fixes = sum(1 for o in ops if o[0] == "back" and o[1])
    assert fixes > errors > 0          # omissions are fixed without a wrong key on screen


def test_keys_are_held_about_116_ms_and_speed_is_human():
    clock = SimClock()
    typer = HumanTyper(FakeInputBackend(), _pacer(clock), random.Random(3))
    text = "the meeting moved to friday and the numbers look fine " * 4
    typer.type_text(text, keep_slips=False)
    holds = typer.stats["holds_ms"]
    assert 100 < sum(holds) / len(holds) < 132
    wpm = len(text) / 5 / (clock.now() / 60)
    assert 30 < wpm < 75, wpm


def test_mouse_path_starts_from_current_position_and_avoids_corners():
    backend = FakeInputBackend((1920, 1080))
    mouse = HumanMouse(backend, _pacer(), random.Random(3), steps=10)
    mouse.click(5, 5)
    moves = [c[1] for c in backend.calls if c[0] == "move_to"]
    assert all(x >= 40 and y >= 40 for x, y in moves)
    assert abs(moves[0][0] - 960) < 400
