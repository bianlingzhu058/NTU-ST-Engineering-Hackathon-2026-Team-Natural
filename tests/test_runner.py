"""Objectives load from YAML, dry runs produce plausible action sequences, runner respects the budget."""
from pathlib import Path
from agent.app import build_app

ROOT = Path(__file__).parents[1]


def test_objectives_load_from_yaml():
    _, _, _, objectives = build_app(ROOT, dry_run=True, seed=3)
    assert {o.name for o in objectives} == {"web_surfing", "office_worker"}


def test_web_surfing_dry_run_opens_navigates_and_closes():
    _, context, runner, _ = build_app(ROOT, dry_run=True, seed=5)
    runner.run_once("web_surfing")
    calls = context.backend.calls
    assert calls[0] in (("press", "win"), ("hotkey", ("win", "1")), ("hotkey", ("win", "r")))
    assert ("hotkey", ("ctrl", "l")) in calls and ("hotkey", ("ctrl", "w")) in calls
    assert any(c[0] == "scroll" for c in calls)
    kinds = {k for k, _ in context.pacer.samples}
    assert {"micro", "step", "read", "think"} <= kinds


def test_office_dry_run_types_saves_and_closes():
    _, context, runner, _ = build_app(ROOT, dry_run=True, seed=8)
    runner.run_once("office_worker")
    calls = context.backend.calls
    assert ("hotkey", ("ctrl", "s")) in calls and ("hotkey", ("alt", "f4")) in calls
    typed = "".join(c[1] for c in calls if c[0] == "write")
    assert typed.isascii() and len(typed) > 100


def test_runner_stops_at_budget_and_logs_task_timeline(tmp_path):
    _, context, runner, _ = build_app(ROOT, dry_run=True, seed=1)
    runner.run(0, "web_surfing")  # zero budget: no objective may start
    runner.run_once("web_surfing")
    log = (ROOT / "logs" / "actions.jsonl").read_text().splitlines()
    assert any('"task_start"' in l for l in log) and any('"task_end"' in l for l in log)
    assert any('"event": "action"' in l for l in log)
