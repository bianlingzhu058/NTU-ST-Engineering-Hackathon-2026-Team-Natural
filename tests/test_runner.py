"""Check objectives load from YAML and bounded runner selection works."""
from pathlib import Path
import random
from agent.app import build_app


def test_objectives_load_from_yaml():
    _, _, runner, objectives = build_app(Path(__file__).parents[1], dry_run=True, seed=3)
    assert {objective.name for objective in objectives} >= {"research_topic", "idle_browse", "office_worker"}
    runner.run(0, "research_topic")
