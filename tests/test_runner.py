"""Check objectives load from YAML and bounded runner selection works."""
from pathlib import Path
import shutil
import random
from agent.app import build_app


def test_objectives_load_from_yaml():
    _, _, runner, objectives = build_app(Path(__file__).parents[1], dry_run=True, seed=3)
    assert {objective.name for objective in objectives} >= {"research_topic", "idle_browse", "office_worker"}
    runner.run(0, "research_topic")


def test_browse_internet_objective_runs_with_fake_backend(tmp_path):
    repository = Path(__file__).parents[1]
    shutil.copytree(repository / "config", tmp_path / "config")
    _, context, runner, objectives = build_app(tmp_path, dry_run=True, seed=7)
    assert "browse_internet" in {objective.name for objective in objectives}
    runner.run_once("browse_internet")
    actions = [name for name, _ in context.backend.calls]
    assert "hotkey" in actions
    assert "scroll" in actions
    assert ("hotkey", ("alt", "f4")) in context.backend.calls
