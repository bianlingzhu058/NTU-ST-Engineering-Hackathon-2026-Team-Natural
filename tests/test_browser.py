"""Browser skills against the simulated desktop: warning pages, dead links, the keyboard fallback."""
from pathlib import Path
from agent.app import build_app
from agent.registry import create_skill
from agent.win.uia import NoUia

ROOT = Path(__file__).parents[1]


def _browser(seed: int, uia: bool = True):
    _, context, runner, _ = build_app(ROOT, mode="dry", seed=seed, log_name=f"logs/test_browser_{seed}.jsonl")
    if not uia: context.uia = NoUia()
    create_skill("open_app").run(context, {"app": "browser", "name": "google chrome", "taskbar_slot": 1})
    return context


def test_certificate_warning_is_cleared_with_advanced_then_proceed():
    context = _browser(1)
    args = {"url": "https://www.dell.com", "read_after": False}
    assert create_skill("go_to_site").run(context, args) == "ready"
    assert args["outcome"] == "recovered" and args["interstitial"] == "advanced+proceed"
    assert args["typed"] == "dell.com"


def test_without_ui_automation_the_bypass_phrase_is_used():
    context = _browser(2, uia=False)
    args = {"url": "https://www.apple.com", "read_after": False}
    create_skill("go_to_site").run(context, args)
    assert "bypass_phrase" in args["interstitial"] and not args["interstitial"].endswith("failed")


def test_navigation_moves_stay_in_the_browser_over_many_steps():
    context = _browser(3)
    create_skill("go_to_site").run(context, {"url": "https://www.samsung.com"})
    outcomes = []
    for _ in range(25):
        args = {"interests": ["price", "support"]}
        create_skill("navigate").run(context, args)
        outcomes.append(args.get("outcome"))
    assert context.look()[2] != "absent"
    assert any(o in ("ready", "opened_background_tab") for o in outcomes)
