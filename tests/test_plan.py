"""Plan groups repeat as a unit, respect the time budget, and stop when the stop file appears."""
from pathlib import Path
from agent.app import build_app
from agent.config import ObjectiveData
from agent.objectives.yaml_objective import YamlObjective
import random

ROOT = Path(__file__).parents[1]


def _context(seed=1):
    _, context, _, _ = build_app(ROOT, mode="dry", seed=seed, log_name="logs/test.jsonl")
    return context


def _objective(plan, params=None):
    return YamlObjective(ObjectiveData("t", 1.0, params or {}, plan), {})


def test_group_repeats_as_a_unit():
    context = _context()
    plan = [{"skill": "open_app", "args": {"name": "edge", "taskbar_slot": 1}},
            {"group": [{"skill": "scroll_and_read", "args": {"bursts": 1}}], "repeat": [3, 3]}]
    _objective(plan).run(context, rng=random.Random(2))
    scrolls = sum(1 for name, _ in context.backend.calls if name == "scroll")
    assert scrolls >= 3


def test_group_stops_repeating_near_the_deadline_so_closing_steps_still_run():
    context = _context()
    context.deadline = context.clock.monotonic() + 40  # 40 s left, min_time_left is 60
    plan = [{"skill": "open_app", "args": {"name": "edge", "taskbar_slot": 1}},
            {"group": [{"skill": "scroll_and_read", "args": {"bursts": 2}}], "repeat": [8, 8], "min_time_left": 60},
            {"skill": "close_app", "args": {"method": "ctrl_w", "tabs": 2}}]
    _objective(plan).run(context, rng=random.Random(3))
    assert ("hotkey", ("ctrl", "w")) in context.backend.calls
    assert sum(1 for name, _ in context.backend.calls if name == "scroll") < 16


def test_stop_file_halts_the_plan_between_actions():
    """The operator's clean abort: the run ends between actions, never mid-keystroke."""
    context = _context()
    context.stop_check = lambda: context.clock.monotonic() > 45  # as if the stop file appeared at 45 s
    plan = [{"skill": "open_app", "args": {"name": "edge", "taskbar_slot": 1}}] + \
           [{"skill": "scroll_and_read", "args": {"bursts": 3}} for _ in range(12)]
    _objective(plan).run(context, rng=random.Random(4))
    assert context.clock.monotonic() < 120  # stopped long before the twelve blocks of reading
    assert sum(1 for name, _ in context.backend.calls if name == "scroll") < 36


def test_params_expand_and_lists_are_sampled():
    context = _context()
    plan = [{"skill": "open_app", "args": {"name": "edge", "taskbar_slot": 1}},
            {"skill": "go_to_url", "args": {"url": "{sites}"}}]
    _objective(plan, {"sites": ["https://a.example", "https://b.example"]}).run(context, rng=random.Random(5))
    typed = "".join(payload for name, payload in context.backend.calls if name == "write")
    assert "a.example" in typed or "b.example" in typed
