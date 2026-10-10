"""GUI-only application open and close skills.

Every strategy here goes through explorer.exe, so the launched app's parent
is explorer.exe in Sysmon, the same as a person clicking. Nothing in this
module may ever call a process API.
"""
from ..registry import register_skill
from .base import BaseSkill, SkillContext

STRATEGIES = ("taskbar", "start_search", "run_dialog")


@register_skill("open_app")
class OpenAppSkill(BaseSkill):
    """Open an application the way a person does, choosing a launch route at random per call.

    args: name (Start search text), taskbar_slot (1..9, app pinned there), run_command
    (what to type in Win+R), strategies (subset of taskbar/start_search/run_dialog).
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        allowed = [s for s in args.get("strategies", STRATEGIES) if s in STRATEGIES]
        if "taskbar" in allowed and not args.get("taskbar_slot"): allowed.remove("taskbar")
        if "run_dialog" in allowed and not args.get("run_command"): allowed.remove("run_dialog")
        if not allowed: allowed = ["start_search"]
        strategy = context.rng.choice(allowed) if context.rng else allowed[0]
        context.pacer.wait("think")
        if strategy == "taskbar":
            context.backend.hotkey("win", str(int(args["taskbar_slot"])))
        elif strategy == "run_dialog":
            context.backend.hotkey("win", "r")
            context.pacer.wait("step")
            context.typer.type_text(str(args["run_command"]))
            context.pacer.wait("step")
            context.backend.press("enter")
        else:
            context.backend.press("win")
            context.pacer.wait("step")
            context.typer.type_text(str(args["name"]))
            context.pacer.wait("step")
            context.backend.press("enter")
        args["strategy"] = strategy
        context.pacer.wait("read")  # app start-up and first look


@register_skill("close_app")
class CloseAppSkill(BaseSkill):
    """Close the foreground application through its normal keyboard shortcut.

    args: method = "ctrl_w" (repeat Ctrl+W up to `tabs` times, safe for browsers,
    never raises the close-all-tabs dialog) or "alt_f4" (plain window close).
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        context.pacer.wait("think")
        if args.get("method", "alt_f4") == "ctrl_w":
            for _ in range(int(args.get("tabs", 3))):
                context.backend.hotkey("ctrl", "w")
                context.pacer.wait("step")
        else:
            context.backend.hotkey("alt", "f4")
        context.pacer.wait("step")
