"""Browser skills: navigate, read, follow links, recover from what the mock sites actually do.

Page content is never read from the screen, and no screenshots are taken: that would cost the
Resource Efficiency criterion for nothing. What the agent does read is the window title, which
is enough to know whether the page loaded, whether it is the TLS interstitial, or whether the
host is dead, and to react the way a person would.

This matters on the organisers' environment specifically. Their intermediate CA expired on
9 Jul 2026, so even the "clean" mock sites currently land on "Your connection isn't private",
and mirrored pages link to real-world hosts that do not resolve inside the VM. A blind macro
types the next URL into an interstitial and the whole run is nonsense; this one clears the
warning like a user, or goes back and tries another site.

Links are followed by keyboard focus (F6 into the page, then Tab, then Enter), which the
telemetry cannot distinguish from a click, and which does not risk clicking something random.
"""
from ..perception import ABSENT, PRIVACY_ERROR, READY, UNREACHABLE, NEW_TAB
from ..registry import register_skill
from .base import BaseSkill, SkillContext, SkillError

BYPASS_PHRASE = "thisisunsafe"  # Chromium's keyboard bypass for a bad certificate


def _pick(context: SkillContext, value):
    """Return a random element when given a list, else the value itself."""
    if isinstance(value, list) and value:
        return context.rng.choice(value) if context.rng else value[0]
    return value


def _require_browser(context: SkillContext, app: str = "browser") -> str:
    """Current page state, raising when the browser is not in front at all."""
    if not context.desktop.available:
        return READY
    title, process, state = context.look(app)
    if state == ABSENT:
        context.note_sighting(state)
        raise SkillError("browser is not the foreground window")
    return state


def _focus_page(context: SkillContext) -> None:
    """Move keyboard focus out of the address bar and into the page body.

    F6 cycles Chromium's focus zones, which is reliable and cannot click anything by accident.
    The occasional click is in the left margin band, where pages are almost always empty.
    """
    context.backend.hotkey("ctrl", "l"); context.pacer.wait("micro")
    context.backend.press("escape"); context.pacer.wait("step")
    context.backend.press("f6"); context.pacer.wait("step")
    if context.rng and context.rng.random() < 0.3:
        width, height = context.backend.screen_size()
        context.mouse.click(context.rng.uniform(width * .03, width * .07), context.rng.uniform(height * .4, height * .7))
        context.pacer.wait("step")


def _focus_interstitial(context: SkillContext) -> None:
    """Put keyboard focus in the body of a certificate warning page.

    Found in the VM on 11 Oct: from the address bar, Edge's F6 lands on the profile button in the
    tab strip, so Tab then Enter opened the profile menu instead of "Advanced". The warning page
    is empty outside its centred text, so one click in the lower-left of the page is safe.
    Escape first closes any menu a stray Enter opened.
    """
    context.backend.press("escape"); context.pacer.wait("step")
    width, height = context.backend.screen_size()
    jitter = context.rng.uniform if context.rng else (lambda a, b: (a + b) / 2)
    context.mouse.click(jitter(width * .08, width * .18), jitter(height * .55, height * .8))
    context.pacer.wait("step")


def _clear_interstitial(context: SkillContext, args: dict, app: str = "browser") -> str:
    """Get past a certificate warning the way a person does, then fall back to the keyboard bypass.

    First attempt is Advanced then "Continue to the site", reached with Tab and Enter. If the
    page is still the interstitial, type Chromium's bypass phrase into the page body.
    """
    gone = lambda: context.desktop.available and context.look(app)[2] != PRIVACY_ERROR
    attempts = []
    # The bypass phrase goes first: it does not depend on the page's Tab order, which differs
    # between Edge's "Privacy error" and "Clock error" pages.
    for strategy in (args.get("strategies") or ["bypass_phrase", "advanced_continue"]):
        attempts.append(strategy)
        if strategy == "advanced_continue":
            _focus_interstitial(context)
            # Two activations: "Advanced", then "Continue to the site". The state is re-read in
            # between, because pressing Enter again on an already-loaded page would click
            # whatever happens to be focused there.
            for press in range(2):
                context.backend.press("tab"); context.pacer.wait("micro")  # one stop: Advanced, then the Continue link
                context.pacer.wait("think" if press == 0 else "step")  # reading the warning before deciding
                context.backend.press("enter"); context.pacer.wait("step")
                if gone(): break
        else:
            _focus_interstitial(context)
            # Typed literally, not through HumanTyper: Chromium matches this keystroke sequence
            # contiguously, and a simulated typo plus backspace would never produce a match.
            for character in BYPASS_PHRASE:
                context.backend.write(character)
                context.pacer.wait("micro")
        context.pacer.wait("read")
        if not context.desktop.available: break
        if context.wait_for(lambda: context.look(app)[2] != PRIVACY_ERROR, float(args.get("timeout", 10.0))):
            args["interstitial"] = "+".join(attempts)
            return context.look(app)[2]
    args["interstitial"] = "+".join(attempts) + ":failed"
    return PRIVACY_ERROR


@register_skill("dismiss_interstitial")
class DismissInterstitialSkill(BaseSkill):
    """Clear a certificate warning if one is showing. args: strategies, timeout."""
    def execute(self, context: SkillContext, args: dict) -> str:
        if _require_browser(context) != PRIVACY_ERROR:
            args["outcome"] = "nothing_to_do"
            return "nothing_to_do"
        args["outcome"] = _clear_interstitial(context, args)
        return args["outcome"]


@register_skill("go_to_url")
class GoToUrlSkill(BaseSkill):
    """Type a URL into the address bar, press Enter, then confirm what actually came up.

    args: url (string or list, one is picked at random), new_tab_probability, timeout,
    bare_host_probability (type "apple.com" instead of the full URL, as people do).
    Outcomes recorded on the log line: ready, recovered (interstitial cleared), unreachable,
    privacy_error (could not clear), unverified (no desktop introspection).
    """
    def execute(self, context: SkillContext, args: dict) -> str:
        app = args.get("app", "browser")
        _require_browser(context, app)
        url = str(_pick(context, args["url"]))
        before = context.perception.page_name(context.desktop.foreground_title())
        if context.rng and context.rng.random() < float(args.get("new_tab_probability", 0.25)):
            context.backend.hotkey("ctrl", "t"); args["new_tab"] = True
            context.pacer.wait("step")
        typed = url
        if context.rng and context.rng.random() < float(args.get("bare_host_probability", 0.45)):
            typed = url.split("://", 1)[-1].rstrip("/")
        args.update(url=url, typed=typed)
        context.backend.hotkey("ctrl", "l")
        context.pacer.wait("step")
        context.typer.type_text(typed)
        context.pacer.wait("step")
        context.backend.press("enter")
        context.pacer.wait("read")  # waiting for the page, then first look at it
        if not context.desktop.available:
            args["outcome"] = "unverified"
            return "unverified"
        context.wait_for(lambda: context.perception.page_name(context.desktop.foreground_title()) != before,
                         float(args.get("timeout", 15.0)))
        state = context.look(app)[2]
        if state == PRIVACY_ERROR:
            state = _clear_interstitial(context, args, app)
            args["outcome"] = "recovered" if state in (READY, NEW_TAB) else state
        elif state == UNREACHABLE:
            context.pacer.wait("think")  # staring at the error page
            if context.rng and context.rng.random() < float(args.get("back_on_dead_page", 0.6)):
                context.backend.hotkey("alt", "left"); args["went_back"] = True
                context.pacer.wait("read")
            args["outcome"] = UNREACHABLE
        else:
            args["outcome"] = READY if state == READY else state
        context.note_sighting(state)
        return args["outcome"]


@register_skill("search")
class SearchSkill(BaseSkill):
    """Search from the browser address bar with a supplied query (list means random pick)."""
    def execute(self, context: SkillContext, args: dict) -> None:
        _require_browser(context)
        query = str(_pick(context, args["query"])); args["query"] = query
        context.backend.hotkey("ctrl", "l")
        context.pacer.wait("step")
        context.typer.type_text(query)
        context.pacer.wait("step")
        context.backend.press("enter")
        context.pacer.wait("read")


@register_skill("scroll_and_read")
class ScrollAndReadSkill(BaseSkill):
    """Scroll the page in bursts with reading pauses and idle mouse drift.

    args: bursts or bursts_range; page_key_probability (use Page Down or End instead of the
    wheel sometimes); skip_on_error (do not pretend to read a dead page).
    """
    def execute(self, context: SkillContext, args: dict) -> int:
        state = _require_browser(context)
        if state in (UNREACHABLE, PRIVACY_ERROR) and args.get("skip_on_error", True):
            context.pacer.wait("think")  # a person looks at the error page before moving on
            args["outcome"] = f"skipped_{state}"
            return 0
        low, high = args.get("bursts_range", [2, 6])
        bursts = int(args.get("bursts") or (context.rng.randint(int(low), int(high)) if context.rng else low))
        args["bursts"] = bursts
        for _ in range(bursts):
            if context.rng and context.rng.random() < float(args.get("page_key_probability", 0.2)):
                context.backend.press(context.rng.choice(["pagedown", "pagedown", "end"]))
                context.pacer.wait("read")
            else:
                context.scroller.scroll_bursts(1)
            if context.rng and context.rng.random() < 0.35:
                context.mouse.drift()
            if context.time_left() < 20:
                break
        args["outcome"] = "read"
        return bursts


@register_skill("follow_link")
class FollowLinkSkill(BaseSkill):
    """Follow a link by focusing the page, Tabbing onto an element and pressing Enter.

    Roughly one attempt in five lands on a button or an input instead of a link and nothing
    happens: that is a person misclicking, and it is logged as no_change rather than retried.
    Mirrored pages often link to hosts that do not resolve in the VM, so a dead page is
    followed by Alt+Left, like a person backing out.
    args: tabs_range, back_probability, timeout.
    """
    def execute(self, context: SkillContext, args: dict) -> str:
        state = _require_browser(context)
        if state in (UNREACHABLE, PRIVACY_ERROR):
            context.pacer.wait("think")
            args["outcome"] = f"skipped_{state}"
            return args["outcome"]
        before = context.perception.page_name(context.desktop.foreground_title())
        _focus_page(context)
        low, high = args.get("tabs_range", [4, 15])
        tabs = context.rng.randint(int(low), int(high)) if context.rng else int(low)
        args["tabs"] = tabs
        for _ in range(tabs):
            context.backend.press("tab")
            context.pacer.wait("micro")
        context.pacer.wait("step")
        context.backend.press("enter")
        context.pacer.wait("read")
        if not context.desktop.available:
            args["outcome"] = "unverified"
            return "unverified"
        changed = context.wait_for(
            lambda: context.perception.page_name(context.desktop.foreground_title()) != before,
            float(args.get("timeout", 10.0)))
        state = context.look()[2]
        if not changed:
            args["outcome"] = "no_change"
        elif state == UNREACHABLE:
            context.pacer.wait("think")
            context.backend.hotkey("alt", "left"); args["went_back"] = True
            context.pacer.wait("read")
            args["outcome"] = "dead_link_back"
        elif state == PRIVACY_ERROR:
            cleared = _clear_interstitial(context, args)
            args["outcome"] = "recovered" if cleared in (READY, NEW_TAB) else cleared
        else:
            args["outcome"] = "followed"
            if context.rng and context.rng.random() < float(args.get("back_probability", 0.35)):
                context.pacer.wait("read")
                context.backend.hotkey("alt", "left"); args["went_back"] = True
                context.pacer.wait("read")
        context.note_sighting(state)
        return args["outcome"]


@register_skill("go_back")
class GoBackSkill(BaseSkill):
    """Press Alt+Left and look at the previous page again."""
    def execute(self, context: SkillContext, args: dict) -> None:
        _require_browser(context)
        context.backend.hotkey("alt", "left")
        context.pacer.wait("read")


@register_skill("reload_page")
class ReloadPageSkill(BaseSkill):
    """Press F5, as people do when a page looks wrong or stale."""
    def execute(self, context: SkillContext, args: dict) -> str:
        _require_browser(context)
        context.backend.press("f5")
        context.pacer.wait("read")
        if not context.desktop.available:
            args["outcome"] = "unverified"
            return "unverified"
        state = context.look()[2]
        if state == PRIVACY_ERROR:
            state = _clear_interstitial(context, args)
        args["outcome"] = state
        return state


@register_skill("close_tab")
class CloseTabSkill(BaseSkill):
    """Close the current tab with Ctrl+W, leaving the browser open."""
    def execute(self, context: SkillContext, args: dict) -> None:
        _require_browser(context)
        context.backend.hotkey("ctrl", "w")
        context.pacer.wait("step")


@register_skill("find_on_page")
class FindOnPageSkill(BaseSkill):
    """Use browser find to locate a phrase (list means random pick), then close the find bar."""
    def execute(self, context: SkillContext, args: dict) -> None:
        state = _require_browser(context)
        if state in (UNREACHABLE, PRIVACY_ERROR):
            args["outcome"] = f"skipped_{state}"
            return
        text = str(_pick(context, args["text"])); args["text"] = text
        context.backend.hotkey("ctrl", "f")
        context.pacer.wait("step")
        context.typer.type_text(text)
        context.pacer.wait("read")
        context.backend.press("escape")
        args["outcome"] = "searched"
