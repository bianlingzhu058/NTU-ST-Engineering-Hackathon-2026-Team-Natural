"""Browser skills composed from input primitives.

Page content is never read from the screen. Links are followed by keyboard
focus (Tab, Enter), which the telemetry cannot distinguish from a click.
"""
from ..registry import register_skill
from .base import BaseSkill, SkillContext


def _pick(context: SkillContext, value):
    """Return a random element when given a list, else the value itself."""
    if isinstance(value, list) and value:
        return context.rng.choice(value) if context.rng else value[0]
    return value


def _focus_page_body(context: SkillContext) -> None:
    """Put keyboard focus on the page body: leave the address bar, click empty space mid-page."""
    context.backend.hotkey("ctrl", "l"); context.pacer.wait("micro")
    context.backend.press("escape"); context.pacer.wait("step")
    w, h = context.backend.screen_size()
    rng = context.rng
    x = rng.uniform(w * 0.15, w * 0.85) if rng else w * 0.5
    y = rng.uniform(h * 0.35, h * 0.75) if rng else h * 0.55
    context.mouse.click(x, y)
    context.pacer.wait("step")


@register_skill("go_to_url")
class GoToUrlSkill(BaseSkill):
    """Navigate the foreground browser to a URL (a list means pick one at random)."""
    def execute(self, context: SkillContext, args: dict) -> None:
        url = str(_pick(context, args["url"])); args["url"] = url
        context.backend.hotkey("ctrl", "l")
        context.pacer.wait("step")
        context.typer.type_text(url)
        context.pacer.wait("step")
        context.backend.press("enter")
        context.pacer.wait("read")


@register_skill("search")
class SearchSkill(BaseSkill):
    """Search from the browser address bar with a supplied query (list means random pick)."""
    def execute(self, context: SkillContext, args: dict) -> None:
        query = str(_pick(context, args["query"])); args["query"] = query
        context.backend.hotkey("ctrl", "l")
        context.pacer.wait("step")
        context.typer.type_text(query)
        context.pacer.wait("step")
        context.backend.press("enter")
        context.pacer.wait("read")


@register_skill("scroll_and_read")
class ScrollAndReadSkill(BaseSkill):
    """Scroll the page in bursts with reading pauses and idle mouse drift. args: bursts or bursts_range."""
    def execute(self, context: SkillContext, args: dict) -> None:
        lo, hi = args.get("bursts_range", [2, 6])
        bursts = int(args.get("bursts") or (context.rng.randint(int(lo), int(hi)) if context.rng else lo))
        args["bursts"] = bursts
        for i in range(bursts):
            context.scroller.scroll_bursts(1)
            if context.rng and context.rng.random() < 0.35: context.mouse.drift()


@register_skill("follow_link")
class FollowLinkSkill(BaseSkill):
    """Follow some link on the page by Tab-focusing a random number of elements and pressing Enter.

    args: tabs_range [min, max]; back_probability (press Alt+Left afterwards, as after a dead page).
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        _focus_page_body(context)
        lo, hi = args.get("tabs_range", [4, 15])
        tabs = context.rng.randint(int(lo), int(hi)) if context.rng else int(lo)
        args["tabs"] = tabs
        for _ in range(tabs):
            context.backend.press("tab")
            context.pacer.wait("micro")
        context.pacer.wait("step")
        context.backend.press("enter")
        context.pacer.wait("read")
        if context.rng and context.rng.random() < float(args.get("back_probability", 0.3)):
            context.backend.hotkey("alt", "left"); args["went_back"] = True
            context.pacer.wait("read")


@register_skill("go_back")
class GoBackSkill(BaseSkill):
    """Press Alt+Left and look at the previous page again."""
    def execute(self, context: SkillContext, args: dict) -> None:
        context.backend.hotkey("alt", "left")
        context.pacer.wait("read")


@register_skill("find_on_page")
class FindOnPageSkill(BaseSkill):
    """Use browser find to locate a phrase (list means random pick)."""
    def execute(self, context: SkillContext, args: dict) -> None:
        text = str(_pick(context, args["text"])); args["text"] = text
        context.backend.hotkey("ctrl", "f")
        context.pacer.wait("step")
        context.typer.type_text(text)
        context.pacer.wait("step")
        context.backend.press("enter")
        context.pacer.wait("read")
        context.backend.press("escape")
