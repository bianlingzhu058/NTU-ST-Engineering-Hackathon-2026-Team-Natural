"""Cross-application clipboard skills: carry a value from one app into another.

A single-app bot is easy to spot; moving real data between applications the way a
person doing research does — copy a source in the browser, paste it into a
spreadsheet — is a visibly complex, human action. The clipboard is real: Ctrl+C in
the browser then Ctrl+V in Calc is an actual cross-process data flow. No new process
is spawned, so this stays telemetry-neutral while adding genuine Action Complexity.
"""
from ..registry import register_skill
from .base import BaseSkill, SkillContext


@register_skill("copy_page_url")
class CopyPageUrlSkill(BaseSkill):
    """Copy the current page's URL, the way a person grabs a link to cite a source.

    Focus the address bar (Ctrl+L), select it (Ctrl+A), copy (Ctrl+C), then Esc back
    to the page. Leaves the URL on the clipboard for a later paste in another app.
    args: expect (window-title substring to confirm the browser is in front first).
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        if args.get("expect"):
            context.verify_window(args["expect"])     # make sure the browser is focused (no-op off Windows)
        context.pacer.wait("think")
        context.backend.hotkey("ctrl", "l")           # focus the address bar
        context.pacer.wait("step")
        context.backend.hotkey("ctrl", "a")           # select the whole URL
        context.pacer.wait("micro")
        context.backend.hotkey("ctrl", "c")           # copy it to the clipboard
        context.pacer.wait("step")
        context.backend.press("escape")               # back to the page
        if hasattr(context.backend, "release_modifiers"):
            context.backend.release_modifiers()
        args["copied"] = True
        context.pacer.wait("read")


@register_skill("paste_into_cell")
class PasteIntoCellSkill(BaseSkill):
    """Paste the clipboard into a spreadsheet cell, as a person logging a gathered source.

    Ctrl+Home to A1, optionally step DOWN to a clear row below the table, optionally type a
    label and Tab to the next cell, then Ctrl+V and Enter. Verifies the spreadsheet window is
    in front first so the paste never lands in the wrong app.
    args: label (text typed before the paste), down (rows to move below A1, default 0),
    expect (window-title substring to confirm, e.g. "Calc").
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        if args.get("expect"):
            context.verify_window(args["expect"])
        if hasattr(context.backend, "release_modifiers"):
            context.backend.release_modifiers()        # Calc is Tab/arrow-heavy; clear any stuck modifier
        context.pacer.wait("think")
        context.backend.hotkey("ctrl", "home")         # jump to A1
        context.pacer.wait("step")
        for _ in range(int(args.get("down", 0) or 0)): # move to a clear row below the table
            context.backend.press("down")
            context.pacer.wait("micro")
        if args.get("label"):
            context.typer.type_text(str(args["label"]), exact=True, key_pause="keydata")
            context.backend.press("tab")
            context.pacer.wait("cell")
        context.backend.hotkey("ctrl", "v")            # paste the copied URL/value
        context.pacer.wait("cell")
        context.backend.press("enter")
        args["pasted"] = True
        context.pacer.wait("read")                     # glance at what was pasted


@register_skill("paste_note")
class PasteNoteSkill(BaseSkill):
    """Paste the clipboard at the current cursor, the way a person drops a copied source into a
    document they are writing.

    Unlike paste_into_cell (which first jumps to a spreadsheet cell with Ctrl+Home), this does NO
    navigation: it pastes wherever the cursor already sits, so it suits a running document whose
    end is already under the cursor. Optionally starts a fresh line and/or types a short label
    (e.g. "Source: ") before the paste.
    args: label (text typed before the paste), newline (press Enter first, default False),
    expect (window-title substring to confirm the right app is in front before pasting).
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        if args.get("expect"):
            context.verify_window(args["expect"])      # confirm the document is focused (no-op off Windows)
        if hasattr(context.backend, "release_modifiers"):
            context.backend.release_modifiers()
        context.pacer.wait("think")
        if args.get("newline"):
            context.backend.press("enter")             # start the source on its own line
            context.pacer.wait("micro")
        if args.get("label"):
            context.typer.type_text(str(args["label"]), exact=True, key_pause="field")
        context.backend.hotkey("ctrl", "v")            # paste the copied URL at the cursor
        args["pasted"] = True
        context.pacer.wait("read")                     # glance at what was pasted
