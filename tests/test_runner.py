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


def test_close_app_never_closes_the_operator_harness():
    from agent.registry import create_skill
    from agent.input.win_state import WindowSensor
    _, context, _, _ = build_app(ROOT, dry_run=True, seed=0)
    context.sensor = WindowSensor(title_provider=lambda: "Synthetic Activity Harness")
    deps = {"backend": context.backend, "pacer": context.pacer, "rng": context.rng}
    create_skill("close_app", **deps).run(context, {"method": "alt_f4"})
    assert ("hotkey", ("alt", "f4")) not in context.backend.calls, "agent tried to close its own UI"


def test_close_app_still_closes_a_real_app():
    from agent.registry import create_skill
    from agent.input.win_state import WindowSensor
    _, context, _, _ = build_app(ROOT, dry_run=True, seed=0)
    context.sensor = WindowSensor(title_provider=lambda: "Untitled 1 - OpenOffice Writer")
    deps = {"backend": context.backend, "pacer": context.pacer, "rng": context.rng}
    create_skill("close_app", **deps).run(context, {"method": "alt_f4", "confirm_close": False})
    assert ("hotkey", ("alt", "f4")) in context.backend.calls


def test_browse_items_is_read_only_and_never_opens_an_item():
    """Driving blind, Enter on a selected item would OPEN a file (or launch an exe in a system
    folder). browse_items must only move the selection and scroll — never Enter / rename / delete."""
    from agent.registry import create_skill
    _, context, _, _ = build_app(ROOT, dry_run=True, seed=2)
    deps = {"backend": context.backend, "pacer": context.pacer, "rng": context.rng}
    create_skill("browse_items", **deps).run(context, {"steps_range": [6, 6]})
    calls = context.backend.calls
    assert ("press", "enter") not in calls, "browse_items pressed Enter — would open a file"
    assert ("press", "f2") not in calls and ("press", "delete") not in calls
    assert ("press", "down") in calls   # it did move through the items


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
    assert ("hotkey", ("ctrl", "1")) in calls   # title styled as a Heading 1 (bigger)
    assert ("hotkey", ("ctrl", "e")) in calls   # title centered (top-centre)
    assert ("hotkey", ("ctrl", "u")) in calls   # title selected and underlined ("highlight")
    typed = "".join(c[1] for c in calls if c[0] == "write")
    assert typed.isascii() and len(typed) > 100


def test_runner_stops_at_budget_and_logs_task_timeline(tmp_path):
    _, context, runner, _ = build_app(ROOT, dry_run=True, seed=1)
    runner.run(0, "web_surfing")  # zero budget: no objective may start
    runner.run_once("web_surfing")
    log = (ROOT / "logs" / "actions.jsonl").read_text().splitlines()
    assert any('"task_start"' in l for l in log) and any('"task_end"' in l for l in log)
    assert any('"event": "action"' in l for l in log)
