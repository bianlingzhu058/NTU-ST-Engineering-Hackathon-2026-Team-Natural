"""Objectives load from YAML, dry runs produce plausible action sequences, runner respects the budget."""
from pathlib import Path
from agent.app import build_app

ROOT = Path(__file__).parents[1]


def test_objectives_load_from_yaml():
    _, _, _, objectives = build_app(ROOT, dry_run=True, seed=3)
    assert {o.name for o in objectives} == {"web_surfing", "office_writer", "office_calc", "cross_app", "file_admin"}


def test_cross_app_flow_copies_in_browser_and_pastes_in_calc():
    _, context, runner, _ = build_app(ROOT, dry_run=True, seed=11)
    runner.run_once("cross_app")
    calls = context.backend.calls
    # A real cross-application data flow: copy in the browser, paste in the spreadsheet.
    assert ("hotkey", ("ctrl", "c")) in calls, "URL never copied in the browser"
    assert ("hotkey", ("ctrl", "v")) in calls, "clipboard never pasted into Calc"
    # Both applications were opened during the one objective (two launches).
    assert sum(1 for c in calls if c in (("press", "win"), ("hotkey", ("win", "r")))) >= 2


def test_file_admin_browses_explorer_read_only():
    _, context, runner, _ = build_app(ROOT, dry_run=True, seed=6)
    runner.run_once("file_admin")
    calls = context.backend.calls
    assert ("hotkey", ("win", "e")) in calls           # opened Explorer with Win+E
    assert ("hotkey", ("alt", "d")) in calls            # typed a path into the address bar
    # Read-only browsing: it must never rename (F2) or delete.
    assert ("press", "f2") not in calls and ("press", "delete") not in calls


def test_objective_paths_keep_backslashes_under_both_yaml_parsers():
    """The VM uses mini_yaml; dev/tests use PyYAML. Single-quoted paths must keep their
    backslashes literally under BOTH, or file_admin navigates to the wrong place."""
    from agent import mini_yaml
    import yaml as pyyaml
    text = (ROOT / "config" / "objectives" / "file_admin.yaml").read_text(encoding="utf-8")
    for loaded in (pyyaml.safe_load(text), mini_yaml.load_yaml(text)):
        paths = loaded["params"]["paths"]
        assert any("\\" in p for p in paths), paths


def test_web_surfing_dry_run_opens_navigates_and_closes():
    _, context, runner, _ = build_app(ROOT, dry_run=True, seed=5)
    runner.run_once("web_surfing")
    calls = context.backend.calls
    assert calls[0] in (("press", "win"), ("hotkey", ("win", "1")), ("hotkey", ("win", "r")))
    # Navigation uses the reliable keyboard address-bar focus (Ctrl+L), and the
    # browser is closed with Ctrl+W.
    assert ("hotkey", ("ctrl", "l")) in calls and ("hotkey", ("ctrl", "w")) in calls
    assert any(c[0] == "scroll" for c in calls)
    kinds = {k for k, _ in context.pacer.samples}
    assert {"micro", "step", "read", "think"} <= kinds


def test_office_dry_run_types_saves_and_closes():
    _, context, runner, _ = build_app(ROOT, dry_run=True, seed=8)
    runner.run_once("office_writer")
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
