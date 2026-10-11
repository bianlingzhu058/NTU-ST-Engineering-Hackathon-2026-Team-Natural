"""GUI-only application open and close skills, with the launch verified before anything is typed.

Every strategy here is a keystroke to the shell, so the launched app's parent in Sysmon Event
ID 1 is explorer.exe, exactly as when a person clicks. Nothing in this module may ever call a
process API: that is what protects the Process Telemetry criterion, and tests/test_no_banned_calls.py
fails the build if a process call ever appears here.

Launch order matters for the logs as well as for reliability:
  taskbar       Win+<slot> on a pinned icon. The most ordinary thing an office worker does.
  start_search  Win, type the app name, Enter. Also brokered through the shell.
  run_dialog    Win+R. Kept as a last resort only: it writes to the RunMRU registry key and
                most office workers never touch it, so it is a small tell in the trace.
"""
from ..perception import ABSENT
from ..registry import register_skill
from .base import BaseSkill, SkillContext, SkillError

STRATEGIES = ("taskbar", "start_search", "run_dialog")
DEFAULT_WEIGHTS = {"taskbar": 3.0, "start_search": 2.0, "run_dialog": 0.0}


def _available(context: SkillContext, args: dict) -> list[str]:
    """Strategies this call may use, dropping any whose arguments are missing."""
    allowed = [s for s in args.get("strategies", STRATEGIES) if s in STRATEGIES]
    if "taskbar" in allowed and not args.get("taskbar_slot"): allowed.remove("taskbar")
    if "run_dialog" in allowed and not args.get("run_command"): allowed.remove("run_dialog")
    if "start_search" in allowed and not args.get("name"): allowed.remove("start_search")
    return allowed or ["start_search"]


def _choose(context: SkillContext, options: list[str], weights: dict) -> str:
    if not context.rng: return options[0]
    scores = [max(0.0, float(weights.get(name, 1.0))) for name in options]
    if not any(scores): scores = [1.0] * len(options)
    return context.rng.choices(options, weights=scores, k=1)[0]


@register_skill("open_app")
class OpenAppSkill(BaseSkill):
    """Open an application the way a person does, then confirm its window actually came up.

    args: app (perception key, default "browser"), name (Start search text), taskbar_slot (1..9),
    run_command (Win+R text), strategies (subset of taskbar/start_search/run_dialog),
    weights (per-strategy weights), timeout (seconds to wait for the window), attempts.
    """
    def execute(self, context: SkillContext, args: dict) -> str:
        app = args.get("app", "browser")
        if context.desktop.available and context.perception.is_app(app, *context.look(app)[:2]):
            args["outcome"] = "already_open"
            return "already_open"
        weights = {**DEFAULT_WEIGHTS, **(args.get("weights") or {})}
        options, tried = _available(context, args), []
        timeout, attempts = float(args.get("timeout", 20.0)), int(args.get("attempts", 2))
        for attempt in range(1, max(1, attempts) + 1):
            remaining = [s for s in options if s not in tried] or options
            strategy = _choose(context, remaining, weights)
            tried.append(strategy)
            context.pacer.wait("think")  # deciding to switch task
            self._send(context, strategy, args)
            context.pacer.wait("read")  # application start-up and first look at the window
            if not context.desktop.available:
                args.update(strategy=strategy, attempts_used=attempt, outcome="unverified")
                return "unverified"
            if context.wait_for(lambda: context.perception.is_app(app, *context.look(app)[:2]), timeout):
                args.update(strategy=strategy, attempts_used=attempt, outcome="opened")
                context.blind_actions = 0
                return "opened"
        args.update(strategy=tried[-1], attempts_used=len(tried), outcome="not_opened")
        raise SkillError(f"{app} window did not appear after {len(tried)} launch attempts")

    def _send(self, context: SkillContext, strategy: str, args: dict) -> None:
        if strategy == "taskbar":
            context.backend.hotkey("win", str(int(args["taskbar_slot"])))
        elif strategy == "run_dialog":
            context.backend.hotkey("win", "r"); context.pacer.wait("step")
            context.typer.type_text(str(args["run_command"])); context.pacer.wait("step")
            context.backend.press("enter")
        else:
            context.backend.press("win"); context.pacer.wait("step")
            context.typer.type_text(str(args["name"])); context.pacer.wait("step")
            context.backend.press("enter")


@register_skill("close_app")
class CloseAppSkill(BaseSkill):
    """Close the foreground application through its normal keyboard shortcut, and confirm it closed.

    args: method = "ctrl_w" (repeat Ctrl+W, the safe browser close: Alt+F4 on Edge raises the
    "Close all tabs?" dialog) or "alt_f4"; tabs (maximum Ctrl+W presses); app (perception key).
    """
    def execute(self, context: SkillContext, args: dict) -> str:
        app = args.get("app", "browser")
        context.pacer.wait("think")
        if args.get("method", "alt_f4") == "ctrl_w":
            presses = 0
            for _ in range(int(args.get("tabs", 6))):
                if context.desktop.available and context.look(app)[2] == ABSENT: break
                context.backend.hotkey("ctrl", "w"); presses += 1
                context.pacer.wait("step")
            args["presses"] = presses
        else:
            context.backend.hotkey("alt", "f4"); context.pacer.wait("step")
            context.backend.press("enter")  # answers "Close all tabs?" when Edge asks
        context.pacer.wait("step")
        if not context.desktop.available:
            args["outcome"] = "unverified"
            return "unverified"
        closed = context.wait_for(lambda: context.look(app)[2] == ABSENT, float(args.get("timeout", 8.0)))
        args["outcome"] = "closed" if closed else "still_open"
        context.blind_actions = 0
        return args["outcome"]
