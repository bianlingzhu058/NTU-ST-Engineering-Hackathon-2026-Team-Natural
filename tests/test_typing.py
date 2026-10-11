"""Typing: exact final text where it matters, no sentence pause inside URLs, real holds and rollover."""
from agent.input.keyboard import HumanTyper, final_text
from tests.helpers import kit


def test_exact_contexts_always_end_with_the_target_text():
    for seed in range(200):
        rng, clock, pacer, persona, backend = kit(seed)
        typer = HumanTyper(backend, pacer, rng, persona)
        for text, ctx in (("coinmarketcap.com", "url"), ("weekly update 42", "filename"), ("=SUM(B2:B6)", "cell"), ("15200", "number")):
            assert final_text(typer.plan(text, ctx)) == text, (seed, text)


def test_corrections_use_backspace_and_the_first_one_is_slowest_on_average():
    firsts, laters = [], []
    for seed in range(300):
        rng, clock, pacer, persona, backend = kit(seed)
        typer = HumanTyper(backend, pacer, rng, persona)
        ops = typer.plan("the quick brown fox jumps over the lazy dog near the river bank", "filename")
        events = typer.schedule(ops, "filename", "transcribe", False)
        downs = [e for e in events if e[3]]
        for prev, cur in zip(downs, downs[1:]):
            if cur[2] == "backspace":
                (laters if prev[2] == "backspace" else firsts).append(cur[0] - prev[0])
    assert firsts and laters and sum(firsts) / len(firsts) > sum(laters) / len(laters)


def test_a_dot_in_a_url_is_an_ordinary_key():
    worst = 0.0
    for seed in range(100):
        rng, clock, pacer, persona, backend = kit(seed)
        typer = HumanTyper(backend, pacer, rng, persona)
        events = [e for e in typer.schedule([("char", c, "") for c in "www.apple.com"], "url", "transcribe", False) if e[3]]
        for prev, cur in zip(events, events[1:]):
            if prev[2] == ".": worst = max(worst, cur[0] - prev[0])
    assert worst < 2000  # milliseconds; the old code could wait 25 s here


def test_every_key_goes_down_and_up_with_a_human_hold_and_some_rollover():
    rng, clock, pacer, persona, backend = kit(4)
    typer = HumanTyper(backend, pacer, rng, persona)
    events = typer.schedule([("char", c, "") for c in "meeting notes for the next release " * 6], "prose", "transcribe", False)
    downs = [e for e in events if e[3]]
    ups = [e for e in events if not e[3]]
    assert len(downs) == len(ups)
    overlaps = 0
    pending = []
    for t, kind, key, down in events:
        if down:
            overlaps += bool(pending); pending.append(key)
        else:
            pending.remove(key)
    share = overlaps / len(downs)
    assert 0.1 < share < 0.45  # Dhakal 2018: rollover on about 25% of keystrokes


def test_typing_drives_the_backend():
    rng, clock, pacer, persona, backend = kit(2)
    HumanTyper(backend, pacer, rng, persona).type_text("hello", ctx="filename")
    typed = "".join(c[1] for c in backend.calls if c[0] == "char_down")
    assert typed.endswith("o") and clock.monotonic() > 0.5
