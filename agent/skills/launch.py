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
            # start_search: open Start, type the name, wait for Windows to resolve it as
            # the Best Match, then press Enter. Enter on a resolved best match launches it
            # reliably — no coordinate guessing. (The earlier failures were Enter firing
            # before the search had resolved.) One `settle` wait is enough for the Best
            # Match to appear and keeps the pre-Enter pause from looking frozen; two `read`
            # waits could stack to ~12s on the long tail. The name is typed EXACT: a typo in
            # the app name would resolve to the wrong Best Match (or none).
            context.backend.press("win")
            context.pacer.wait("settle")              # Start opens / search box ready
            context.typer.type_text(str(args["name"]), exact=True)
            context.pacer.wait("settle")              # let Windows resolve the Best Match
            context.backend.press("enter")
        args["strategy"] = strategy
        # Clear any modifier (esp. the Windows key) left stuck by the launch over VNC, before
        # the next skill's keystrokes — otherwise a dropped Win key-up turns later Tab/Ctrl
        # presses into Win+Tab / Win+Ctrl+... (Task View, new virtual desktops).
        if hasattr(context.backend, "release_modifiers"):
            context.backend.release_modifiers()
        # Confirm the app window is actually in front before handing off to the next skill.
        # `expect` is a title substring (e.g. "Edge", "Writer", "Calc"). With sensing we wait
        # adaptively for that window (reliable, and avoids typing into the Start menu or a
        # half-open window — the cause of the URL-in-search and screen-lock failures). Without
        # sensing (dry run / non-Windows) verify_window returns None and we keep the old fixed
        # wait, so behaviour is unchanged there. Never hard-fails: an unconfirmed window still
        # proceeds after a human beat.
        expect = args.get("expect")
        confirmed = context.verify_window(expect, tries=int(args.get("expect_tries", 8))) if expect else None
        args["window_confirmed"] = confirmed
        if confirmed:
            context.pacer.wait("step")   # window is up — brief beat, then the next skill acts
        else:
            context.pacer.wait("read")   # no sensing, or not confirmed: original app-start pause


@register_skill("maximize_window")
class MaximizeWindowSkill(BaseSkill):
    """Square up the foreground window to full screen with Win+Up, the way a person
    maximizes a freshly opened window before working in it.

    Keyboard shortcut through the shell (no coordinate guessing), and it standardizes
    the window to a known full-screen size — which is the state the fraction-of-screen
    mouse positions in scroll_and_read and hover_nav already assume. Telemetry-neutral.

    args: first (wait for a just-opened fresh-profile browser to come up first).
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        if args.get("first"):
            context.pacer.wait("browser_ready")   # let the fresh browser window appear first
        context.pacer.wait("step")                # brief beat before reaching for the window menu
        # Alt+Space opens the foreground window's system menu, "x" picks Maximize. This is
        # deterministic (Win+Up is intercepted by Win11 Snap layouts and can mis-fire).
        # If the window is already maximized, Maximize is disabled and this is a harmless no-op.
        context.backend.hotkey("alt", "space")
        context.pacer.wait("step")
        context.backend.press("x")
        context.pacer.wait("step")   # brief beat; go_to_url does its own settle before typing, so no double-settle here


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
            # FIX (OpenOffice/editors): closing may raise a "Save changes?" prompt.
            # Its default button is Save, so a confirming Enter dismisses it. Harmless
            # when no prompt appears. Only for alt_f4; browsers use ctrl_w above.
            if args.get("confirm_close", True):
                context.pacer.wait("settle")
                context.backend.press("enter")
        context.pacer.wait("step")
