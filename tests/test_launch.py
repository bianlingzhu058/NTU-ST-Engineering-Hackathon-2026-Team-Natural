"""Launching must be verified: the agent never types into a window that did not appear."""
import random
import pytest
from pathlib import Path
from agent.app import build_app
from agent.perception import ABSENT
from agent.skills.base import AbortRun, SkillError
from agent.skills.launch import OpenAppSkill
from agent.win.fake_desktop import FakeDesktop

ROOT = Path(__file__).parents[1]


def _context(seed=3, **overrides):
    _, context, _, _ = build_app(ROOT, mode="dry", seed=seed, log_name="logs/test.jsonl")
    for key, value in overrides.items(): setattr(context, key, value)
    return context


def test_open_app_reports_the_strategy_it_used_and_that_the_window_appeared():
    context = _context()
    args = {"app": "browser", "name": "edge", "taskbar_slot": 1, "strategies": ["taskbar", "start_search"]}
    assert OpenAppSkill().run(context, args) == "opened"
    assert args["strategy"] in ("taskbar", "start_search") and args["outcome"] == "opened"


def test_open_app_retries_a_second_strategy_then_fails_loudly_when_nothing_opens():
    """A dead taskbar slot must not leave the agent typing a URL into the desktop."""
    context = _context()
    context.desktop = FakeDesktop(random.Random(1), startup_polls=10 ** 6)
    context.backend._observer = context.desktop.observe
    args = {"app": "browser", "name": "edge", "taskbar_slot": 1, "timeout": 4, "attempts": 2,
            "strategies": ["taskbar", "start_search"]}
    with pytest.raises(SkillError):
        OpenAppSkill().run(context, args)
    assert args["outcome"] == "not_opened" and args["attempts_used"] == 2


def test_open_app_does_nothing_when_the_app_is_already_in_front():
    context = _context()
    OpenAppSkill().run(context, {"app": "browser", "name": "edge", "taskbar_slot": 1})
    args = {"app": "browser", "name": "edge", "taskbar_slot": 1}
    assert OpenAppSkill().run(context, args) == "already_open"


def test_run_aborts_rather_than_typing_blindly_when_the_desktop_is_lost():
    context = _context(max_blind_actions=1)
    with pytest.raises(AbortRun):
        context.note_sighting(ABSENT)


def test_run_dialog_is_not_used_unless_it_is_the_only_option():
    """Win+R writes RunMRU, so it stays a fallback: default weight is zero."""
    context = _context()
    chosen = set()
    for _ in range(30):
        args = {"app": "browser", "name": "edge", "taskbar_slot": 1, "run_command": "msedge",
                "strategies": ["taskbar", "start_search", "run_dialog"]}
        context.desktop = FakeDesktop(random.Random(7))
        context.backend._observer = context.desktop.observe
        OpenAppSkill().run(context, args)
        chosen.add(args["strategy"])
    assert "run_dialog" not in chosen and chosen <= {"taskbar", "start_search"}
