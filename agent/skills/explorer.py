"""File Explorer skills: browse folders the way a person does.

Explorer IS explorer.exe, so opening a window and clicking through folders is natively part
of the shell — authentic process lineage with no launch trick, and it generates exactly the
file-system activity a real user produces. These skills are READ-ONLY: they open, navigate and
skim folders, and never rename, move or delete anything.
"""
from ..registry import register_skill
from .base import BaseSkill, SkillContext


def _pick(context: SkillContext, value):
    if isinstance(value, list) and value:
        return context.rng.choice(value) if context.rng else value[0]
    return value


@register_skill("open_explorer")
class OpenExplorerSkill(BaseSkill):
    """Open a File Explorer window with Win+E, as a person does. args: expect (optional title
    substring to confirm; the title is usually the folder name, so it is normally left off)."""
    def execute(self, context: SkillContext, args: dict) -> None:
        context.pacer.wait("think")
        context.backend.hotkey("win", "e")
        if hasattr(context.backend, "release_modifiers"):
            context.backend.release_modifiers()   # clear the Windows key before any later Tab/arrow
        expect = args.get("expect")
        confirmed = context.verify_window(expect, tries=int(args.get("expect_tries", 8))) if expect else None
        args["window_confirmed"] = confirmed
        context.pacer.wait("step" if confirmed else "read")


@register_skill("explorer_navigate")
class ExplorerNavigateSkill(BaseSkill):
    """Go to a folder by typing its path into the address bar (Alt+D focuses it), the way a
    person types a path. Paths are typed EXACT (a typo'd path goes nowhere). %USERPROFILE% and
    other environment variables expand in the address bar. args: path (string or list)."""
    def execute(self, context: SkillContext, args: dict) -> None:
        path = str(_pick(context, args["path"])); args["path"] = path
        context.pacer.wait("think")               # decide where to navigate
        context.backend.hotkey("alt", "d")        # focus the address bar
        context.pacer.wait("read")                # look at the address bar before typing a path
        # Typed at the slower "url" pace so it is visibly keyed (a path takes a moment to type),
        # but EXACT — no typos: a typo'd path fails to resolve, and the address bar's autocomplete
        # makes backspace-corrections unreliable (same reason URLs are typed exact).
        context.typer.type_text(path, exact=True, key_pause="url")
        context.pacer.wait("step")
        context.backend.press("enter")
        if hasattr(context.backend, "release_modifiers"):
            context.backend.release_modifiers()
        context.pacer.wait("page_load")           # the folder's contents load


@register_skill("browse_items")
class BrowseItemsSkill(BaseSkill):
    """Skim a folder: arrow down through the items with a scroll or two, the way a person glances
    over a folder's contents. STRICTLY read-only: it NEVER presses Enter — driving blind, the
    selected item could be a file (Enter would open it in another app) or, in a system folder, an
    executable (Enter would launch it). Navigation between folders is done only through the address
    bar (explorer_navigate). args: steps_range [min,max] arrow presses."""
    def execute(self, context: SkillContext, args: dict) -> None:
        rng = context.rng
        # Rest the pointer over the file list on the right, like a hand on the mouse while reading.
        w, h = context.backend.screen_size()
        rest_x = rng.uniform(w * 0.55, w * 0.80) if rng else w * 0.65
        rest_y = rng.uniform(h * 0.35, h * 0.60) if rng else h * 0.48
        context.mouse.move(rest_x, rest_y)
        lo, hi = args.get("steps_range", [3, 7])
        steps = rng.randint(int(lo), int(hi)) if rng else int(lo)
        args["steps"] = steps
        for i in range(steps):
            context.backend.press("down")                 # move the selection down the list (no Enter)
            context.pacer.wait("read" if (rng and rng.random() < 0.3) else "step")
            if i == steps // 2:
                context.scroller.scroll_bursts(1)         # a scroll partway through
