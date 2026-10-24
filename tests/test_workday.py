"""Workday mode, run on fake input with a simulated clock: the to do list on the page always matches
the bot's own copy, runs end near the set time, every app is closed, and the messy editor always
reaches its planned text."""
import random
from pathlib import Path
import pytest
from agent.app import build_app
from agent.behaviour import params
from agent.day.doc import Composer, Unit, WriterDoc
from agent.day.report import checks, run_one

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("minutes,seed", [(5, 1), (15, 2), (15, 7), (30, 3)])
def test_workday_runs_clean(minutes, seed):
    day, context, summary = run_one(ROOT, minutes, seed)
    c = checks(day, context, summary)
    assert c["todo_page_matches_plan"]
    assert c["overrun_s"] < 30
    assert c["apps_left_open"] == []
    assert summary["todo_text"].splitlines()[0]           # a dated title
    assert all(status in ("done", "failed", "started", "open", "deleted") for _, status, _ in summary["items"])


def test_never_two_identical_lines():
    day, _, summary = run_one(ROOT, 60, 4)
    labels = [label for label, status, _ in summary["items"] if status != "deleted"]
    assert len(labels) == len(set(labels))


def test_messy_editor_always_reaches_the_plan():
    saved = dict(params._overrides)
    heavy = {"edit.park_p": 0.7, "edit.rewrite_p": 0.7, "edit.forget_word_p": 0.5, "edit.extra_word_p": 0.4}
    try:
        for seed in range(60):
            _, ctx, _, _ = build_app(ROOT, dry_run=True, seed=seed)
            params._overrides.update(heavy)                 # build_app resets overrides from config
            doc = WriterDoc(ctx, short_lines=seed % 2 == 0)
            units = [Unit("Met with design about the new budget.", alt="Short call with design on the budget."),
                     Unit("We agreed to keep the order small this month."),
                     Unit("Sarah sends the final numbers by Friday.", alt="Sarah will send numbers on Friday.", newline_after=1),
                     Unit("Open question is the monitor stand.")]
            comp = Composer(doc, random.Random(seed), lambda s: None, extras=["Check the shared folder later."])
            target = comp.write(units)
            assert doc.text == target
    finally:
        params._overrides.clear(); params._overrides.update(saved)


def test_every_rule_has_a_source_and_a_kind():
    for group, name, value, source, conf in params.table():
        assert source and conf in "HMLDU", name
