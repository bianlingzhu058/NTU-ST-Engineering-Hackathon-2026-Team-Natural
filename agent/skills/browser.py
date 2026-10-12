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


# Edge chrome layout (fractions of screen height), used to aim the mouse like a
# person: the address bar runs across the very top, the site's own top nav strip
# sits just under it.
_ADDRESS_BAR_Y = 0.08       # Edge address bar (for a MAXIMIZED window); nudge if off
_NAV_STRIP_Y = 0.24         # a site's top navigation menu (World / US / Politics ...)


def _click_address_bar(context: SkillContext) -> None:
    """Move the mouse to the address bar and click it, the way a person does
    (no Ctrl+L keyboard shortcut), then select-all so the new URL replaces the old."""
    w, h = context.backend.screen_size()
    rng = context.rng
    x = rng.uniform(w * 0.30, w * 0.60) if rng else w * 0.45
    y = h * _ADDRESS_BAR_Y
    context.mouse.click(x, y)                 # click into the address bar
    context.pacer.wait("step")
    context.backend.hotkey("ctrl", "a")       # select existing text so typing replaces it


@register_skill("go_to_url")
class GoToUrlSkill(BaseSkill):
    """Navigate to a URL using the keyboard focus shortcut for the address bar.

    Ctrl+L focuses Edge's address bar regardless of where/how the window sits, so
    this is reliable (no screen-position guessing) and is a common power-user
    habit. In telemetry it is indistinguishable from a mouse click on the bar.
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        url = str(_pick(context, args["url"])); args["url"] = url
        if args.get("first"):
            context.pacer.wait("browser_ready")   # let the just-opened browser come up (covers window settling too)
        else:
            context.pacer.wait("settle")          # fresh page: brief settle before focusing the bar
        context.backend.hotkey("ctrl", "l")       # focus the address bar (reliable)
        context.pacer.wait("step")
        context.typer.type_text(url, exact=True)  # URLs verbatim: no typos, no "." sentence pause
        context.pacer.wait("step")
        context.backend.press("enter")
        context.pacer.wait("page_load")  # let the page finish loading before interacting


@register_skill("open_new_tab")
class OpenNewTabSkill(BaseSkill):
    """Open a new tab (Ctrl+T), visit a site, glance at it, then close the tab (Ctrl+W) to
    return — the way a person opens a fresh tab to check something and closes it after.

    Self-contained so the tab count stays bounded. A tab is NOT a new process, so this is
    telemetry-neutral, but it adds a distinct, visibly human action. The URL is typed exact.
    args: url (string or list); close_after (close the tab when done, default true).
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        url = str(_pick(context, args["url"])); args["url"] = url
        context.pacer.wait("think")                 # decide to open a new tab
        context.backend.hotkey("ctrl", "t")         # new tab (address bar gets focus)
        context.pacer.wait("settle")
        context.backend.hotkey("ctrl", "l")         # make sure the address bar is focused
        context.pacer.wait("step")
        context.typer.type_text(url, exact=True)    # URL verbatim
        context.pacer.wait("step")
        context.backend.press("enter")
        context.pacer.wait("page_load")
        # Park the mouse on the right and scroll a little, reading the new tab.
        w, h = context.backend.screen_size()
        rng = context.rng
        rest_x = rng.uniform(w * 0.88, w * 0.96) if rng else w * 0.92
        rest_y = rng.uniform(h * 0.35, h * 0.6) if rng else h * 0.5
        context.mouse.move(rest_x, rest_y)
        bursts = rng.randint(2, 4) if rng else 2
        for _ in range(bursts):
            context.scroller.scroll_bursts(1)
        args["bursts"] = bursts
        context.pacer.wait("read")
        if args.get("close_after", True):
            context.backend.hotkey("ctrl", "w")     # close this tab -> back to the previous one
            args["closed"] = True
            context.pacer.wait("step")


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
    """Scroll the page, with the mouse resting over on the right side (near the
    scrollbar) the whole time, the way a person does while reading. args: bursts
    or bursts_range."""
    def execute(self, context: SkillContext, args: dict) -> None:
        lo, hi = args.get("bursts_range", [2, 6])
        bursts = int(args.get("bursts") or (context.rng.randint(int(lo), int(hi)) if context.rng else lo))
        args["bursts"] = bursts
        # Park the pointer on the right side (near the scrollbar) and leave it there.
        w, h = context.backend.screen_size()
        rng = context.rng
        rest_x = rng.uniform(w * 0.88, w * 0.96) if rng else w * 0.92
        rest_y = rng.uniform(h * 0.35, h * 0.6) if rng else h * 0.5
        context.mouse.move(rest_x, rest_y)
        for i in range(bursts):
            context.scroller.scroll_bursts(1)
        # Mouse stays put over on the right while reading — no aimless drifting.


@register_skill("hover_nav")
class HoverNavSkill(BaseSkill):
    """Move the mouse along the site's top navigation menu and hover (no click),
    so dropdowns reveal — the way a person browses a nav bar deciding where to go.

    Hovers a few spots across the top nav strip. Sites that have hover menus
    (e.g. AP News: World / U.S. / Politics) show their dropdowns; sites that don't
    simply have the pointer pass over the header harmlessly.
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        w, h = context.backend.screen_size()
        rng = context.rng
        y = h * _NAV_STRIP_Y
        hovers = rng.randint(2, 4) if rng else 2
        args["hovers"] = hovers
        for _ in range(hovers):
            x = rng.uniform(w * 0.15, w * 0.75) if rng else w * 0.4
            context.mouse.move(x, y)          # hover, do NOT click
            context.pacer.wait("read")        # pause so the dropdown shows and is "read"


@register_skill("follow_link")
class FollowLinkSkill(BaseSkill):
    """Follow a link using keyboard focus (Tab to a link, Enter), then go Back.

    Keyboard link-following is reliable (no screen-position guessing) and in
    telemetry is indistinguishable from a mouse click — a link is followed, the
    page navigates. The mock sites are homepage-only, so the link usually 404s;
    we glance, then Alt+Left back, exactly as a person does after a dead link.

    args: tabs_range [min, max]; back_probability (press Alt+Left afterwards).
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        rng = context.rng
        # Put focus on the page (Esc off the address bar) then Tab onto a link.
        context.backend.press("escape")
        context.pacer.wait("step")
        lo, hi = args.get("tabs_range", [3, 10])
        tabs = rng.randint(int(lo), int(hi)) if rng else int(lo)
        args["tabs"] = tabs
        for _ in range(tabs):
            context.backend.press("tab")
            context.pacer.wait("micro")
        context.pacer.wait("step")
        context.backend.press("enter")
        context.pacer.wait("page_load")  # let the followed link's page load
        if rng and rng.random() < float(args.get("back_probability", 1.0)):
            context.pacer.wait("read")                 # glance at the (likely 404) page
            context.backend.hotkey("alt", "left"); args["went_back"] = True
            context.pacer.wait("page_load")            # wait for the original page to come back


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
        context.typer.type_text(text, exact=True)  # short find term: type it clean
        context.pacer.wait("step")
        context.backend.press("enter")
        context.pacer.wait("read")
        context.backend.press("escape")
