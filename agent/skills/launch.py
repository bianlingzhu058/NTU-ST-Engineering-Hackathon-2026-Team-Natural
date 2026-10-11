"""Open and close applications the way a person does, and confirm what actually came up.

Every route is a keystroke to the Windows shell, so the new process's parent in Sysmon Event ID 1
is explorer.exe, exactly as when a person clicks. Nothing here may call a process API;
tests/test_no_banned_calls.py fails the build if one appears.

Routes (launch-method shares are a researcher synthesis, marked U in the parameters table):
  taskbar       Win+<slot> on a pinned icon.
  start_search  Win, type the app name, look at the results, Enter. Enter pressed before Windows
                has found the app runs a Bing web search in Edge (seen on the VM 11 Oct), so the
                person reads the result list first (one KLM M plus the search response).
  run_dialog    Win+R. Never chosen by default: it writes RunMRU and few office workers use it.

After each attempt the agent waits for the window. If it did not appear, it looks again before
trying another route, because a slow app that opens late must not be launched twice.
"""
from ..behaviour.params import P
from ..perception import ABSENT
from ..registry import register_skill
from .base import BaseSkill, SkillContext, SkillError

STRATEGIES = ("taskbar", "start_search", "run_dialog")


def _available(args: dict) -> list[str]:
    allowed = [s for s in args.get("strategies", ["taskbar", "start_search"]) if s in STRATEGIES]
    if "taskbar" in allowed and not args.get("taskbar_slot"): allowed.remove("taskbar")
    if "run_dialog" in allowed and not args.get("run_command"): allowed.remove("run_dialog")
    if "start_search" in allowed and not args.get("name"): allowed.remove("start_search")
    return allowed or ["start_search"]


@register_skill("open_app")
class OpenAppSkill(BaseSkill):
    """args: app (perception key), name (Start search text), taskbar_slot, run_command, strategies,
    weights (per strategy), timeout (seconds to wait for the window), attempts."""
    def execute(self, context: SkillContext, args: dict) -> str:
        app = args.get("app", "browser")
        is_up = lambda: context.perception.is_app(app, *context.look(app)[:2])
        if context.desktop.available and is_up():
            args["outcome"] = "already_open"
            return "already_open"
        options, tried = _available(args), []
        weights = {**P("launch.weights"), **(args.get("weights") or {})}
        timeout, attempts = float(args.get("timeout", 20.0)), int(args.get("attempts", 2))
        for attempt in range(1, max(1, attempts) + 1):
            remaining = [s for s in options if s not in tried] or options
            scores = [max(0.0, float(weights.get(s, 1.0))) for s in remaining]
            strategy = context.rng.choices(remaining, weights=scores if any(scores) else None, k=1)[0] \
                if context.rng else remaining[0]
            tried.append(strategy)
            context.wait("M")  # deciding to open the app
            self._send(context, strategy, args)
            if not context.desktop.available:
                context.pacer.sleep(context.pacer.duration("M"))
                args.update(strategy=strategy, attempts_used=attempt, outcome="unverified")
                return "unverified"
            if context.wait_for(is_up, timeout) or context.wait_for(is_up, 3.0):
                args.update(strategy=strategy, attempts_used=attempt, outcome="opened")
                context.blind_actions = 0
                context.memory.tabs = max(context.memory.tabs, 1) if app == "browser" else context.memory.tabs
                return "opened"
            if self._via_start_center(context, args, is_up):
                args.update(strategy=strategy + "+start_center", attempts_used=attempt, outcome="opened")
                context.blind_actions = 0
                return "opened"
            context.typer.press("escape")  # close a Start menu left open by a missed attempt
        args.update(strategy=tried[-1], attempts_used=len(tried), outcome="not_opened")
        raise SkillError(f"{app} window did not appear after {len(tried)} launch attempts")

    def _via_start_center(self, context: SkillContext, args: dict, is_up) -> bool:
        """OpenOffice sometimes opens its Start Center instead of the module asked for; a person
        then clicks "Text Document" or "Spreadsheet". The button is found by name through UIA."""
        label = args.get("start_center_button")
        if not label or context.desktop.foreground_process() != "soffice.bin": return False
        button = context.uia.find(context.desktop.foreground_hwnd(), "button", (str(label).lower(),))
        if not button: return False
        context.wait("M")
        context.mouse.click(*button.center, button.width, button.height)
        return context.wait_for(is_up, 15.0)

    def _send(self, context: SkillContext, strategy: str, args: dict) -> None:
        typer = context.typer
        if strategy == "taskbar":
            typer.combo("win", str(int(args["taskbar_slot"])))
        elif strategy == "run_dialog":
            typer.combo("win", "r"); context.wait("M")
            typer.type_text(str(args["run_command"]), ctx="query")
            context.pacer.sleep(context.pacer.duration("poll") * 2)
            typer.press("enter")
        else:
            typer.press("win")
            context.pacer.sleep(context.rng.uniform(*P("system.start_menu_s")))  # Start menu opening
            typer.type_text(str(args["name"]), ctx="query")
            context.wait("M")  # reading the result list before pressing Enter
            context.pacer.sleep(context.rng.uniform(*P("system.search_response_s")))  # search response
            typer.press("enter")


@register_skill("close_app")
class CloseAppSkill(BaseSkill):
    """Close the foreground application with its normal shortcut and confirm it went away.

    args: app; method = "alt_f4" (default) or "ctrl_w" (close browser tabs one by one).
    """
    def execute(self, context: SkillContext, args: dict) -> str:
        app = args.get("app", "browser")
        gone = lambda: context.look(app)[2] == ABSENT
        context.wait("M")
        if args.get("method", "alt_f4") == "ctrl_w":
            presses = 0
            for _ in range(int(args.get("tabs", 8))):
                if context.desktop.available and gone(): break
                context.typer.combo("ctrl", "w"); presses += 1
                context.pacer.sleep(context.rng.uniform(*P("nav.between_tab_close_s")))
            args["presses"] = presses
        else:
            context.typer.combo("alt", "f4")
        if not context.desktop.available:
            args["outcome"] = "unverified"
            return "unverified"
        closed = context.wait_for(gone, float(args.get("timeout", 8.0)))
        if not closed and context.look(app)[2] != ABSENT and app in ("writer", "calc"):
            # "Save changes?" means the save did not happen; do not discard silently, leave it for the log
            args["outcome"] = "still_open"
            return "still_open"
        args["outcome"] = "closed" if closed else "still_open"
        context.memory.tabs = 0 if app == "browser" and closed else context.memory.tabs
        context.blind_actions = 0
        return args["outcome"]
