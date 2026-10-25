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
            name = args["name"]
            if isinstance(name, list): name = context.rng.choice(name) if context.rng else name[0]
            args["name"] = name
            context.typer.type_text(str(name), exact=True)
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
    """Square up the foreground window to full screen the way a person does: nothing if it is
    already full screen, else a double click on the title bar.

    Full screen is the state the fraction-of-screen mouse positions in scroll_and_read and
    hover_nav assume.

    args: first (wait for a just-opened fresh-profile browser to come up first).
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        if args.get("first"):
            context.pacer.wait("browser_ready")   # let the fresh browser window appear first
        from ..win.uia import front_window
        state = front_window()
        if state is None or state[0]:
            return                                # already full screen (Edge usually opens so), or no sensing
        # Not full screen: double click the title bar, like a person. The old Alt+Space, x flashed the
        # window menu at the top left corner over Edge's profile icon on every open (VM run 3, 25 Oct).
        left, top, right, _ = state[1]
        x = left + (right - left) * context.rng.uniform(0.35, 0.6) if context.rng else (left + right) / 2
        context.mouse.move(x, top + 14)
        context.pacer.wait("step")
        context.backend.click()
        context.pacer.tiny(context.rng.uniform(0.07, 0.16) if context.rng else 0.1)
        context.backend.click()
        context.pacer.wait("step")


@register_skill("close_app")
class CloseAppSkill(BaseSkill):
    """Close the foreground application through its normal keyboard shortcut.

    args: method = "ctrl_w" (repeat Ctrl+W up to `tabs` times, safe for browsers,
    never raises the close-all-tabs dialog) or "alt_f4" (plain window close).
    """
    HARNESS_TITLE = "Synthetic Activity Harness"   # the operator UI — must never be closed by the agent

    def execute(self, context: SkillContext, args: dict) -> None:
        context.pacer.wait("think")
        # Safety net: never close the operator harness itself. If the target app failed to open,
        # the foreground window can be the harness UI — an Alt+F4 (or a browser Ctrl+W) would then
        # close the run's own controls mid-session. If sensing says the harness is in front, skip
        # the close. (Sensing unavailable => proceed as before; nothing changes off-Windows.)
        sensor = context.sensor
        if (sensor is not None and getattr(sensor, "available", False)
                and sensor.foreground_matches([self.HARNESS_TITLE])):
            args["skipped_close_on_harness"] = True
            context.pacer.wait("step")
            return
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
