"""Browser skills for Chrome on the organisers' mock sites.

What a visit looks like, and where each choice comes from (behaviour/params.py has the numbers):

  go_to_site   Ctrl+L, type the bare host (a 2 to 4 letter prefix plus autocomplete when the
               site was visited before), Enter, then wait for the title to settle. Typing a host
               is about 12% of navigations in field logs, so it is used to enter a new site only.
  certificate  the mock sites' certificates expired on 9 Jul 2026, so Chrome shows "Privacy
               error". A person clicks "Advanced", reads, then clicks "Proceed to ... (unsafe)".
               The agent does the same with the mouse, finding both by name through UI
               Automation; typing Chrome's "thisisunsafe" is the fallback.
  read_page    the page's total dwell is a Weibull draw (shape below 1: many short visits, a few
               long ones; Liu 2010, Weinreich 2008), spent reading and scrolling (scroll.py).
  navigate     one move from the measured mix: follow a link (with a new-tab persona), back,
               switch tab, find on page, reload, forward. Links are chosen from what UI
               Automation reports, weighted to visible and upper-left links as clicks are in
               Weinreich 2008, and clicked with the mouse. Without UIA, find-on-page plus Enter
               opens a link whose text matches what the person was looking for.

Window titles say whether a page loaded, is the certificate warning, or is a dead host; nothing
reads page pixels.
"""
import re
from urllib.parse import urlsplit
from ..behaviour.dist import clamp, weighted, weibull
from ..behaviour.params import P
from ..perception import ABSENT, NEW_TAB, PRIVACY_ERROR, READY, UNREACHABLE, normalise
from ..registry import register_skill
from .base import BaseSkill, SkillContext, SkillError, require_app

BYPASS_PHRASE = "thisisunsafe"
HOSTNAME = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)+")
PAGE_KINDS = {"apnews.com": "article", "coursera.org": "hub", "aws.amazon.com": "hub", "coinmarketcap.com": "hub",
              "coingecko.com": "hub", "coinbase.com": "product", "apple.com": "product", "samsung.com": "product",
              "dell.com": "product", "amazon.com": "product"}
SKIP_LINK_WORDS = ("sign in", "log in", "login", "sign up", "register", "cart", "bag", "privacy", "cookie",
                   "terms", "skip to", "accessibility", "javascript", "menu", "close", "search")


def _host(url: str) -> str:
    text = url if "://" in url else "https://" + url
    return (urlsplit(text).hostname or url).lower()


def _kind(host: str) -> str:
    bare = host[4:] if host.startswith("www.") else host
    return PAGE_KINDS.get(bare, "product")


def _is_dead(context: SkillContext, title: str, host: str) -> bool:
    """Chrome titles a DNS-failure page with the bare hostname, so a title equal to the host plus
    almost no links means the mirror's link pointed at a host that does not exist offline."""
    state = context.perception.page_state(title, "chrome.exe", "browser")
    if state == UNREACHABLE: return True
    page = context.perception.page_name(title)
    if page and HOSTNAME.fullmatch(page):  # error pages are titled with the failing host, real pages are not
        if not context.uia.available:  # a site titled with its own domain (e.g. "Amazon.com") is not dead
            site = ".".join(host.split(".")[-2:])
            return not page.endswith(site)
        return len(context.uia.elements(context.desktop.foreground_hwnd(), "hyperlink")) < 3
    return False


def _dead_dwell(context: SkillContext) -> float:
    shape, scale, low, high = P("nav.dead_page_dwell_s")
    return clamp(weibull(context.rng, shape, scale), low, high)


def read_current_page(context: SkillContext, args: dict, state: str) -> None:
    """Spend a Weibull page dwell reading and scrolling; results are added to ``args``."""
    if state in (UNREACHABLE, PRIVACY_ERROR, ABSENT):
        context.pacer.sleep(_dead_dwell(context))
        args["read"] = f"skipped_{state}"
        return
    kind = context.memory.page_kind
    shape, scale = P("page.dwell_weibull")[kind]
    low, high = P("page.dwell_clamp_s")
    revisit = context.memory.went_back
    dwell = clamp(weibull(context.rng, shape, scale * (P("page.revisit_factor") if revisit else 1.0)), low, high)
    dwell = min(dwell, max(10.0, context.time_left()))  # only the very last page can be cut short
    result = context.scroller.read_page(kind, dwell, context.page_region(), context.stop_check, context.time_left)
    context.memory.went_back = False
    args["read"] = result


def _settle(context: SkillContext, before: str, host: str, args: dict, timeout: float = 15.0) -> str:
    """Wait for the page, clear a certificate warning, classify the result, and record it."""
    title = context.wait_stable_title(before, timeout)
    state = context.perception.page_state(title, context.desktop.foreground_process(), "browser")
    if state == PRIVACY_ERROR:
        state = clear_interstitial(context, args)
        args["outcome"] = "recovered" if state in (READY, NEW_TAB) else state
    elif state != ABSENT and _is_dead(context, title, host):
        args["outcome"] = UNREACHABLE
        context.pacer.sleep(_dead_dwell(context))
        context.typer.combo("alt", "left")  # back out of a dead link, as people do
        context.memory.went_back = True
        context.wait_stable_title(title, 8.0)
        state = UNREACHABLE
    else:
        args["outcome"] = state
    context.note_sighting(state)
    return state


def clear_interstitial(context: SkillContext, args: dict) -> str:
    """Advanced, then Proceed, with the mouse; Chrome's keyboard bypass phrase as the fallback."""
    hwnd = context.desktop.foreground_hwnd()
    still_error = lambda: context.look()[2] == PRIVACY_ERROR
    steps = []
    advanced = context.uia.find(hwnd, "button", ("advanced",))
    if advanced:
        context.wait("M")  # reading the warning
        context.mouse.click(*advanced.center, advanced.width, advanced.height); steps.append("advanced")
        context.pacer.sleep(context.pacer.duration("poll") * 2)
        proceed = None
        for _ in range(3):
            proceed = context.uia.find(hwnd, "hyperlink", ("proceed", "continue to"))
            if proceed: break
            context.pacer.wait("poll")
        if proceed:
            context.wait("M")  # reading the expanded text before deciding
            context.mouse.click(*proceed.center, proceed.width, proceed.height); steps.append("proceed")
            title = context.wait_stable_title("", 12.0)
            if not still_error():
                args["interstitial"] = "+".join(steps)
                return context.look()[2]
    # fallback: click an empty part of the page, then type the bypass phrase exactly
    left, top, right, bottom = context.page_region()
    context.mouse.click(left + (right - left) * 0.08, top + (bottom - top) * 0.75, 60, 60)
    context.typer.type_exact(BYPASS_PHRASE)
    steps.append("bypass_phrase")
    context.wait_for(lambda: not still_error(), 10.0)
    args["interstitial"] = "+".join(steps) + ("" if not still_error() else ":failed")
    return context.look()[2]


def _type_host(context: SkillContext, url: str, args: dict) -> str:
    host = _host(url)
    typed = host[4:] if host.startswith("www.") else host  # people type the bare host
    p_partial, low, high = P("nav.partial_host")
    if host in context.memory.visited_hosts and context.rng.random() < p_partial:
        typed = typed[:context.rng.randint(low, high)]  # Chrome completes the rest inline
    args.update(url=url, typed=typed)
    context.typer.combo("ctrl", "l")
    context.pacer.sleep(context.rng.uniform(*P("nav.after_ctrl_l_s")))
    context.typer.type_text(typed, ctx="url", familiar=host in context.memory.visited_hosts)
    context.pacer.sleep(context.pacer.duration("poll"))  # glance at the suggestion
    context.typer.press("enter")
    return host


@register_skill("go_to_site")
class GoToSiteSkill(BaseSkill):
    """Enter a site by typing its host. args: url (string or list), timeout."""
    def execute(self, context: SkillContext, args: dict) -> str:
        require_app(context, "browser")
        urls = args["url"] if isinstance(args["url"], list) else [args["url"]]
        fresh = [u for u in urls if _host(u) not in context.memory.visited_hosts] or urls
        url = context.rng.choice(fresh) if context.rng else fresh[0]
        before = context.desktop.foreground_title()
        context.wait("M")
        host = _type_host(context, url, args)
        context.memory.visited_hosts.add(host)
        context.memory.host, context.memory.page_kind = host, _kind(host)
        context.memory.history_depth += 1
        if not context.desktop.available:
            context.pacer.sleep(context.pacer.duration("M") * 2)
            args["outcome"] = "unverified"
            return "unverified"
        state = _settle(context, before, host, args, float(args.get("timeout", 15.0)))
        if args.pop("read_after", True): read_current_page(context, args, state)
        return state


@register_skill("read_page")
class ReadPageSkill(BaseSkill):
    """Read the current page on its own (the plans read inside go_to_site and navigate instead)."""
    def execute(self, context: SkillContext, args: dict) -> dict:
        read_current_page(context, args, require_app(context, "browser"))
        args["outcome"] = "read"
        return args


def _link_weight(element, region, vh_bottom: float) -> float:
    left, top, right, bottom = region
    x, y = element.center
    w = P("nav.link_above_fold_w") if y < vh_bottom else 1.0
    if x - left < 520 and y - top < 400: w *= P("nav.link_upper_left_w")
    return w


def _choose_link(context: SkillContext, interests: list[str]):
    region = context.page_region()
    links = [e for e in context.uia.elements(context.desktop.foreground_hwnd(), "hyperlink")
             if region[0] <= e.center[0] <= region[2] and region[1] <= e.center[1] <= region[3]
             and len(e.name) >= 3 and not any(word in e.name.lower() for word in SKIP_LINK_WORDS)]
    if not links: return None
    weights = []
    for link in links:
        w = _link_weight(link, region, region[3])
        if any(term in link.name.lower() for term in interests): w *= P("nav.interest_weight")
        weights.append(w)
    return context.rng.choices(links, weights=weights, k=1)[0]


@register_skill("navigate")
class NavigateSkill(BaseSkill):
    """One navigation move from the measured mix, then reading the page it leads to.

    One log line per page visit: logging the move and the reading separately made short and long
    gaps alternate (lag-1 correlation about -0.3), a pattern human logs do not have.
    args: interests (link words), timeout.
    """
    def execute(self, context: SkillContext, args: dict) -> str:
        read_after = args.pop("read_after", True)
        state = self._move(context, args)
        if read_after:
            current = context.look()[2] if context.desktop.available else READY
            read_current_page(context, args, current)
        return state

    def _move(self, context: SkillContext, args: dict) -> str:
        state = require_app(context, "browser")
        memory, rng = context.memory, context.rng
        mix = dict(P("nav.mix"))
        if memory.history_depth < 2: mix.pop("back", None)
        if memory.tabs < 2: mix.pop("switch_tab", None)
        if not memory.went_back: mix.pop("forward", None)
        mix.pop("typed", None)  # entering a new site is go_to_site's job in the plan
        if state in (UNREACHABLE, PRIVACY_ERROR): mix = {"back": 1.0}
        move = weighted(rng, mix)
        args["move"] = move
        before = context.desktop.foreground_title()
        interests = [str(t).lower() for t in (args.get("interests") or [])]
        context.wait("click" if move == "link" else "M")
        if move == "link":
            return self._follow(context, args, before, interests)
        if move == "back":
            context.typer.combo("alt", "left"); memory.went_back = True
            memory.history_depth = max(0, memory.history_depth - 1)
        elif move == "forward":
            context.typer.combo("alt", "right"); memory.went_back = False
        elif move == "switch_tab":
            context.typer.combo("ctrl", "tab")
        elif move == "reload":
            context.typer.press("f5")
        elif move == "find":
            return self._find(context, args, interests)
        if not context.desktop.available:
            args["outcome"] = "unverified"
            return "unverified"
        return _settle(context, before, memory.host, args, float(args.get("timeout", 10.0)))

    def _follow(self, context: SkillContext, args: dict, before: str, interests: list[str]) -> str:
        memory = context.memory
        link = _choose_link(context, interests) if context.uia.available else None
        if link is None:
            return self._find(context, args, interests, follow=True)
        args["link"] = link.name[:60]
        new_tab = memory.tabs < P("nav.max_tabs") and context.rng.random() < context.persona.new_tab_p
        if new_tab:
            context.mouse.move(*link.center, link.width, link.height)
            context.backend.key_event("ctrl", True)
            context.pacer.tiny(context.rng.uniform(*P("nav.ctrl_click_lead_s")))
            context.mouse.press_button()
            context.backend.key_event("ctrl", False)
            memory.tabs += 1
            args.update(new_tab=True, outcome="opened_background_tab")
            return "opened_background_tab"
        context.mouse.click(*link.center, link.width, link.height)
        memory.history_depth += 1
        return _settle(context, before, memory.host, args, float(args.get("timeout", 10.0)))

    def _find(self, context: SkillContext, args: dict, interests: list[str], follow: bool = False) -> str:
        """Ctrl+F a word the person is looking for; with ``follow``, Escape then Enter opens the
        matched link (Chromium leaves the match focused), the keyboard way to click it."""
        term = context.rng.choice(interests) if interests else "more"
        args.update(find=term, via="find")
        before = context.desktop.foreground_title()
        context.typer.combo("ctrl", "f")
        context.pacer.sleep(context.rng.uniform(*P("nav.after_find_open_s")))
        context.typer.type_text(term, ctx="query")
        context.wait("M")  # looking at the highlighted matches
        context.typer.press("escape")
        if not follow:
            args["outcome"] = "searched"
            return "searched"
        context.pacer.sleep(context.rng.uniform(*P("nav.after_find_open_s")))
        context.typer.press("enter")
        if not context.desktop.available:
            args["outcome"] = "unverified"
            return "unverified"
        title = context.wait_stable_title(before, 6.0)
        if title == before:
            args["outcome"] = "no_link_matched"
            return "no_link_matched"
        context.memory.history_depth += 1
        return _settle(context, title, context.memory.host, args, 2.0)


@register_skill("close_browser_tabs")
class CloseTabsSkill(BaseSkill):
    """Close background tabs first sometimes, then the browser (Alt+F4 closes all tabs in Chrome)."""
    def execute(self, context: SkillContext, args: dict) -> str:
        require_app(context, "browser")
        context.wait("M")
        closed = 0
        while context.memory.tabs > 1 and context.rng.random() < P("nav.close_tabs_first_p"):
            context.typer.combo("ctrl", "w"); context.memory.tabs -= 1; closed += 1
            context.pacer.sleep(context.rng.uniform(*P("nav.between_tab_close_s")))
        args["tabs_closed"] = closed
        args["outcome"] = "done"
        return "done"
