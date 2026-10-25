"""The work behind each to do line. One task at a time; every task has a goal and an end state
(done, failed or started).

Each task is a Python generator: it does its desktop actions and ``yield``s at safe points (after
reading a page, between sheet rows, between paragraphs). The workday decides at those points
whether a break, another task or the end of the run cuts in. A cut office or hybrid task keeps its
place, because its window and cursor stay where they were; picking it up later is "Alt+Tab back,
Ctrl+End, carry on". A cut websurf task just counts as started; doing it again is a fresh browse
of the same site (agreed 24 Oct).
"""
from ..behaviour.dist import clamp, ln_median
from ..behaviour.params import P
import re
from . import eyes as E
from .content import RECIPES, SAVED_NOTE, linked_note, note_sentences, outcome_note, sheet_rows, today
from .doc import Composer, Unit, WriterDoc
from .todo import CalcSheet

ERROR_TITLES = ["404", "403", "forbidden", "not found", "can't reach", "cannot", "error", "isn't available", "problem loading"]
BROWSER = ["Microsoft\u200b Edge", "Microsoft Edge", "Edge"]


class ReadFailed(RuntimeError):
    """The page gave nothing to work with; the task ends as an honest failure on the list."""


class Task:
    kind = ""
    resumable = True

    def __init__(self, day, item):
        self.day, self.item, self.ctx = day, item, day.ctx
        self.window = None
        self.status, self.note = "open", ""
        self.gen = None
        self.started_at = None
        self.next_need_s = 0.0   # seconds the step after this checkpoint runs with no check (a sheet row + save)
        self.record: list[dict] = []   # what really happened, step by step (design 25 Oct)

    def steps(self):
        raise NotImplementedError
        yield

    def resume_prelude(self) -> None:
        """Back to where the task was: Alt+Tab to its window, a moment to get going again."""
        if self.window is not None and self.window in self.day.desk.mru:
            self.day.desk.focus(self.window, "resume " + self.item.label)
        median, sigma = P("pause.resume_lag_s")
        self.day.wait(clamp(ln_median(self.ctx.rng, median, sigma), 0.6, 4.0))
        doc = getattr(self.window, "doc", None) if self.window else None
        if isinstance(doc, WriterDoc) and doc.cur != len(doc.text):
            doc.anchor_end()

    def pause_here(self) -> None:
        """Being cut: save what is open so nothing is lost (first save names the file)."""
        if self.window is not None and self.window.app in ("writer", "calc") and self.window in self.day.desk.mru:
            self.save()

    def save(self) -> None:
        pass

    # shared browser helpers
    def skill(self, name: str, args: dict) -> dict:
        return self.day.desk._skill(name, args)

    def browse_to(self, url: str, new_tab: bool | None = None):
        """Open the site in the browser (a new tab most of the time when a page is already open), then
        look at it and react like a person (observe). Returns what the page shows, or [] when the
        site never came up; the record says why."""
        desk = self.day.desk
        fresh = not desk.find("browser")
        win = desk.browser(self.item.label)
        self.window = win
        if not fresh:
            if new_tab is None: new_tab = self.ctx.rng.random() < 0.6
            if new_tab and win.tabs < P("tabs.max_open"):
                self.ctx.pacer.wait("think")
                self.ctx.backend.hotkey("ctrl", "t"); win.tabs += 1
                self.ctx.pacer.wait("settle")
        self.skill("go_to_url", {"url": url, "first": False})
        self.day.mark_app("browser")
        self.url = url
        self.day.eyes.see(url)
        state, page = self.observe(url)
        self.rec("page", site=self.site_name(url), state=state)
        return page if state == "ok" else []

    def look(self, visible: bool = False, kinds=E.PAGE_KINDS):
        return self.day.eyes.read(BROWSER, kinds, visible)

    def rec(self, what: str, **kw) -> None:
        """One line in the task's record of what happened; the result and the note come from it."""
        self.record.append({"what": what, **kw})
        self.day.log({"event": "saw", "task": self.item.label, "what": what, **kw})

    def observe(self, url: str, patient: bool = True):
        """Look at the page and react like a person (design 25 Oct):
        still loading: wait 2 to 3 s, sometimes move the mouse, look again, up to about 20 s;
        error: pause, sometimes move the mouse, refresh once (F5), look again;
        pop-up: click Agree / Accept, look again.
        Returns (state, page): "ok", "error" (still after the refresh) or "loading" (never came up)."""
        ctx, eyes = self.ctx, self.day.eyes
        if not eyes.available:                              # no eyes (should not happen on the VM): title only
            sensor = ctx.sensor
            if sensor is None or not getattr(sensor, "available", False): return "ok", [True]
            title = (sensor.foreground_title() or "").lower()
            return ("error", []) if any(e in title for e in ERROR_TITLES) else ("ok", [True])
        waited, refreshed, clicked = 0.0, False, 0
        limit = P("task.page_give_up_s") if patient else 10.0
        while not ctx.pacer.stopped():
            page = self.look()
            state, detail = E.page_state(page)
            if state == "ok":
                return "ok", page
            if state == "popup" and clicked < 2:
                button = E.popup_button(page)
                ctx.pacer.wait("read")
                self.day.desk.click_el(button)
                if hasattr(eyes, "click"): eyes.click(button)
                clicked += 1
                self.rec("popup", button=detail)
                ctx.pacer.wait("settle")
                continue
            if state == "popup" and len(E.content(page)) >= 3:
                # clicked Accept twice and the page is there behind it (Samsung keeps a hidden "Accept"
                # link in the page): carry on like a person, not "not loading"
                return "ok", page
            if state == "error":
                if refreshed:
                    return "error", page
                ctx.pacer.wait("read")                     # look at the error a moment
                if ctx.rng.random() < 0.5: ctx.mouse.drift()
                ctx.backend.press("f5"); refreshed = True    # one refresh, like a person
                ctx.pacer.wait("page_load"); waited += 3.0
                continue
            if waited >= limit:                              # still empty after about 20 s
                return "loading", page
            ctx.pacer.wait("page_load"); waited += 3.0
            if ctx.rng.random() < 0.4: ctx.mouse.drift()
        return "loading", []

    def click_link(self, link) -> list:
        """Click a link the eyes found and look at what opens. An error page gets one refresh; still an
        error: go back. Returns the new page, or [] for a dead end (recorded)."""
        ctx, day = self.ctx, self.day
        ctx.pacer.wait("think")
        day.desk.click_el(link)
        day.log({"event": "click_link", "link": link.name[:60]})
        target = link.url or (self.url.rstrip("/") + "/" + link.name.split()[0].lower())
        day.eyes.see(target)
        ctx.pacer.wait("page_load")
        state, page = self.observe(target, patient=False)
        self.rec("link", name=link.name[:40], state=state)
        if state != "ok":
            ctx.pacer.wait("read")
            ctx.backend.hotkey("alt", "left")               # back to where it was
            day.eyes.see(self.url)
            ctx.pacer.wait("page_load")
            return []
        return page

    def look_again_for(self, find, word: str = ""):
        """The page works but what the task needs is not in view: scroll and look again (twice), maybe
        Ctrl+F the word, like a person searching a page. Returns what was found, or None."""
        for attempt in range(3):
            got = find(self.look())
            if got: return got
            if attempt == 1 and word:
                self.skill("find_on_page", {"text": word})
            else:
                self.skill("scroll_and_read", {"bursts_range": [1, 2]})
        return None

    def site_failed(self) -> bool:
        """True when the last page the task opened ended as an error or never loaded."""
        pages = [r for r in self.record if r["what"] == "page"]
        return bool(pages) and pages[-1]["state"] != "ok"

    def say(self, key: str, **kw) -> str:
        return ", " + outcome_note(self.ctx.rng, key, **kw)

    def scan_for(self, find, words=(), tries: int = 3):
        """Look for something on the screen, scrolling down a bit between looks."""
        for i in range(tries):
            found = find(self.look(visible=True))
            if found: return found
            self.skill("scroll_and_read", {"bursts_range": [1, 2]})
        return None

    def copy_from_page(self, el) -> None:
        """Select the text with the mouse and copy it; often Ctrl+C more than once to be sure."""
        ctx = self.ctx
        self.day.desk.drag_select(el)
        ctx.pacer.wait("step")
        for i in range(ctx.rng.choice([1, 1, 2, 2, 3]) if ctx.rng.random() < P("copy.repeat_p") else 1):
            if i: ctx.pacer.tiny(ctx.rng.uniform(0.15, 0.45))
            ctx.backend.hotkey("ctrl", "c")
        ctx.pacer.wait("step")

    def split_screen(self, left, right) -> None:
        """Edge on the left half, the document on the right, the way people move things from a page into
        a sheet or note. Only the tasks that copy across do this; the desk checks it really happened."""
        desk = self.day.desk
        if desk.split_pair == (left, right): return
        desk.split(left, right)
        if hasattr(self.day.eyes, "split"): self.day.eyes.split()   # simulator: right hand columns now off screen

    def site_name(self, url: str) -> str:
        host = url.split("//")[-1].split("/")[0].replace("www.", "")
        return host.split(".")[0]

    def maybe_trim_tabs(self) -> None:
        win = self.window
        if win and win.app == "browser" and win.tabs > 2 and self.ctx.rng.random() < P("tabs.close_some_p") / 3:
            n = self.ctx.rng.randint(1, win.tabs - 1)
            for _ in range(n):
                self.ctx.backend.hotkey("ctrl", "w"); self.ctx.pacer.wait("step")
            win.tabs -= n
            self.day.log({"event": "closed_tabs", "n": n})


class Browse(Task):
    """Websurf: open the site, read, follow a link that fits what the person came for (found and
    clicked by its name), read that page. A link that is an error gets one refresh; still an error,
    the bot goes back and tries ONE other link, then finishes (Kellyn, 25 Oct). The note says what
    happened: "done", "done but some pages error", or "page error, try again later"."""
    kind = "websurf"
    resumable = False

    def steps(self):
        spec, rng, day = self.item.spec, self.ctx.rng, self.day
        url = spec["site"]
        page = self.browse_to(url)
        if not page:
            self.status, self.note = "failed", self.say("site_error", site=self.site_name(url))
            return
        self.skill("scroll_and_read", {"bursts_range": [2, 5]})
        yield "read"
        if rng.random() < 0.3: self.skill("hover_nav", {})
        need = spec.get("need")
        if need:
            yield from self._reach_goal(url, page, need, spec.get("goal", "read"))
            return
        if spec.get("find") and rng.random() < 0.4: self.skill("find_on_page", {"text": spec["find"]})
        words = list(spec.get("find", ()))
        looks, tried, errors = rng.randint(*P("task.courses_to_look")), set(), 0
        n = 0
        while n < looks:
            pick = self.scan_for(lambda els: [l for l in E.links(els, words) if l.name not in tried])
            if not pick:
                break
            choice = pick[0] if rng.random() < 0.6 else rng.choice(pick[:8])
            tried.add(choice.name)
            if self.click_link(choice):
                self.skill("scroll_and_read", {"bursts_range": [1, 4]})
                self.ctx.backend.hotkey("alt", "left"); day.eyes.see(url)
                self.ctx.pacer.wait("page_load")
                n += 1
            else:
                errors += 1
                if errors >= 2: break                      # one other link after an error, then stop
            if n < looks: yield "link"
        self.maybe_trim_tabs()
        self.status = "done"
        self.note = self.say("links_error") if errors else self.say("done")

    def _reach_goal(self, url, home, need, goal):
        """The line asks for one thing (Kellyn, 25 Oct): done only when that thing was got, never when the
        bot merely saw the word. Ctrl+F the word first.
        read: a sentence or headline with the word, on this page; it is read and its gist goes on the list.
        open: the link with the word is clicked and its page must show something new; a 404 (after one
        refresh) or a page with nothing new is "<word> page down, try again later"."""
        rng, site, low = self.ctx.rng, self.site_name(url), need.lower()
        yield "find " + need                                  # a natural stop before the search
        self.skill("find_on_page", {"text": need})
        if goal == "read":
            must = self.item.spec.get("answer", "")
            found = self.look_again_for(lambda els: E.answers(els, low, must), need)
            self.rec("goal", goal=goal, word=need, got=found[0].name[:60] if found else "")
            if not found:
                self.status, self.note = "failed", self.say("missing", site=site, what=low)
                return
            self.ctx.pacer.wait("read")                       # read the answer (no stop here: it is got)
            self.status, self.note = "done", ", " + E.gist(found[0].name, must)
            return
        # the goal link may be one random browsing skips (contact): no skip list here
        link = self.look_again_for(lambda els: [l for l in E.links(els, [need], avoid=()) if low in l.name.lower()], need)
        if not link:
            self.rec("goal", goal=goal, word=need, got="")
            self.status, self.note = "failed", self.say("missing", site=site, what=low)
            return
        page = self.click_link(link[0])
        before = {e.name for e in E.content(home)}
        new = [e for e in E.content(page) if e.name not in before]
        self.rec("goal", goal=goal, word=need, got=f"{len(new)} new things on the page")
        if len(new) < 3:                                      # 404, or only the same menu bar again
            if page:
                self.ctx.backend.hotkey("alt", "left"); self.day.eyes.see(url)
            self.status, self.note = "failed", self.say("goal_down", site=site, what=low)
            return
        self.skill("scroll_and_read", {"bursts_range": [1, 3]})
        self.status, self.note = "done", self.say("done")


def rng_between(rng, a: float, b: float) -> float:
    return rng.uniform(a, b) if rng else (a + b) / 2


class CryptoPrices(Task):
    """Hybrid: read the CoinGecko price table, then put 2 to 4 coins (name, price, market cap) and a
    SUM into Calc, Edge and Calc side by side. Each number is taken off the page: sometimes selected
    and copied, otherwise looked up again (Ctrl+F) and typed."""
    kind = "hybrid"

    def steps(self):
        day, rng, ctx = self.day, self.ctx.rng, self.ctx
        url = self.item.spec["site"]
        page = self.browse_to(url)
        coins = E.coingecko_coins(page) if page else []
        if page and not coins:
            coins = self.look_again_for(E.coingecko_coins, "Bitcoin") or []
        if not coins:
            if page: self.rec("missing", site="coingecko", thing="prices")
            self.status = "failed"
            self.note = self.say("site_error", site="coingecko") if not page else self.say("missing", site="coingecko", what="prices")
            return
        short = day.minutes < P("plan.short_run_minutes")      # the 3.5 min demo: one coin, Coin + Price
        if not short: self.skill("scroll_and_read", {"bursts_range": [1, 3]})
        focus = (self.item.spec.get("_coin") or "").lower()
        first = [c for c in coins if c["name"].lower() == focus]
        others = [c for c in coins if c not in first and c["name"] not in ("USDC", "USDS")]
        k = 1 if short else rng.randint(*P("task.coins_to_record"))
        chosen = first + rng.sample(others[:8], min(len(others[:8]), k - len(first)))
        yield "read prices"
        browser = self.window
        sheet_win = day.reuse_window("crypto")
        if sheet_win:
            day.desk.focus(sheet_win, "crypto sheet"); sheet = sheet_win.doc
            sheet.go_next_free_row()
            self.split_screen(browser, sheet_win)
        else:
            sheet_win = day.desk.new_document("calc", "crypto sheet")
            sheet_win.extra["topic"] = "crypto"
            sheet = CalcSheet(ctx, ["Coin", "Price"] if short else ["Coin", "Price", "Market cap"], sum_cols=[])   # no total: adding market caps means nothing
            sheet_win.doc = sheet
            self.split_screen(browser, sheet_win)
            day.desk.ensure_front(sheet_win, "sheet")
            sheet.start()
        self.window = sheet_win
        day.mark_app("calc")
        self.hidden = set()                                  # columns the bot could not see for some coin
        for n, coin in enumerate(chosen):
            self.split_screen(browser, sheet_win)              # again after a break or a cut (no op if still split)
            day.desk.ensure_front(sheet_win, "row")
            cells = [coin["name"], self._from_page(browser, sheet_win, coin["name"], "price_text", coin["price"])]
            if not short:
                cells.append(self._from_page(browser, sheet_win, coin["name"], "cap_text", coin["market_cap"]))
            sheet.add_cells(cells)
            sheet_win.dirty = True
            if n < len(chosen) - 1:
                self.next_need_s = P("task.row_need_s"); yield "row"; self.next_need_s = 0.0
        self.save()
        self.item.found = {"kind": "crypto", "file": sheet_win.file,
                           "facts": [(c["name"], c["price"], c["market_cap"]) for c in chosen]}
        self.status = "done"
        self.note = ", " + rng.choice(SAVED_NOTE).format(file=sheet_win.file)
        if self.hidden:                                      # a number it could not reach: started, tbc (Kellyn)
            self.status, self.note = "started", ", started, " + rng.choice(SAVED_NOTE).format(file=sheet_win.file)

    def _from_page(self, browser, sheet_win, coin: str, which: str, value: str):
        """One cell, only from what is on screen (Kellyn, 25 Oct): go to the page, find the coin, scroll the
        table sideways if the number is cut off (Shift + wheel, tested on the VM), point at the number, then
        copy it (most of the time) or read and type it. A number the bot cannot see is never typed from
        memory: the cell stays empty and the list says so. ``value`` is only what the first look saw."""
        day, ctx, rng = self.day, self.ctx, self.ctx.rng

        def enter():
            day.desk.focus(browser, "look up " + coin); day.mark_app("browser")
            self.skill("find_on_page", {"text": coin})
            el = self._reach_cell(coin, which)
            if el is None:
                self.hidden.add(which)
                day.log({"event": "cell_not_shown", "coin": coin, "what": which})
                day.desk.focus(sheet_win, "leave it empty"); day.mark_app("calc")
                return
            self._point_at(el)
            if el.kind != "hyperlink" and rng.random() < P("copy.calc_p"):
                self.copy_from_page(el)
                day.desk.focus(sheet_win, "paste"); day.mark_app("calc")
                ctx.backend.hotkey("ctrl", "v")
                day.log({"event": "copied", "what": el.name})
            else:
                day.desk.focus(sheet_win, "type it"); day.mark_app("calc")
                number = el.name.lstrip("$").replace(",", "")
                if len(number) > 7:                          # a long number: type part, glance back at it
                    cut = rng.randint(3, len(number) - 3)
                    ctx.typer.type_text(number[:cut], ctx="number")
                    ctx.pacer.wait("read")
                    ctx.typer.type_text(number[cut:], ctx="number")
                else:
                    ctx.typer.type_text(number, ctx="number")
        return enter

    def _view(self):
        """Where the page shows on screen (left, top, right, bottom), without Edge's own bars and the
        page scroll bar. None when nothing can say (then everything counts as shown)."""
        eyes = self.day.eyes
        if getattr(eyes, "viewport", None): return eyes.viewport
        if not getattr(eyes, "uia", None): return None
        from ..win.uia import front_window
        st = front_window()
        if not st: return None
        l, t, r, b = st[1]
        return (l + 8, t + 130, r - 25, b - 10)

    @staticmethod
    def _shown(el, view) -> bool:
        if view is None: return True
        l, t, r, b = view
        return el.left >= l and el.right <= r and el.top >= t and el.bottom <= b

    def _reach_cell(self, coin: str, which: str):
        """The coin's cell, WHOLE on screen. Above or below the screen: mouse wheel up or down over the
        table; cut off on the right: Shift + wheel down (table moves right); on the left or under the coin
        name column: Shift + wheel up. Looks again after each little scroll, and stops when the cell is
        shown or the page no longer moves (a person gives up there too)."""
        ctx, eyes = self.ctx, self.day.eyes
        key = "price_el" if which == "price_text" else "cap_el"
        last, scrolls = None, 0
        for attempt in range(14):
            row = next((c for c in E.coingecko_coins(self.look()) if c["name"] == coin), None)
            el = (row or {}).get(key)
            if el is None: return None
            view = self._view()
            if view is not None:                               # the coin name column stays put when the table
                l, t, r, b = view                              # scrolls, and cells slide UNDER it
                view = (max(l, row["name_el"].right + 4), t, r, b)
            if self._shown(el, view):
                if scrolls: self.rec("scrolled", coin=coin, cell=which, scrolls=scrolls)
                return el
            if view is None: return None
            pos = (el.left, el.top)
            if pos == last:                                    # the last scroll moved nothing: give up
                self.day.log({"event": "cell_unreachable", "coin": coin, "cell": which, "at": list(pos), "view": list(view)})
                return None
            last = pos
            l, t, r, b = view
            if el.top < t or el.bottom > b:                    # up or down first
                ctx.mouse.move(rng_between(ctx.rng, l + 0.3 * (r - l), l + 0.7 * (r - l)), (t + b) / 2)
                ctx.pacer.wait("step")
                for _ in range(2):
                    ctx.backend.scroll(1 if el.top < t else -1)   # wheel up = page up
                    ctx.pacer.tiny(ctx.rng.uniform(0.08, 0.2))
                if hasattr(eyes, "vscroll"): eyes.vscroll(-2 if el.top < t else 2)
            else:                                              # then sideways
                right = el.right > r
                ctx.mouse.move(rng_between(ctx.rng, l + 0.3 * (r - l), l + 0.7 * (r - l)), (el.top + el.bottom) / 2)
                ctx.pacer.wait("step")
                ctx.backend.key_event("shift", True)
                for _ in range(2):
                    ctx.backend.scroll(-1 if right else 1)     # wheel down + Shift = table to the right
                    ctx.pacer.tiny(ctx.rng.uniform(0.08, 0.2))
                ctx.backend.key_event("shift", False)
                if hasattr(eyes, "hscroll"): eyes.hscroll(2 if right else -2)
            scrolls += 1
            ctx.pacer.wait("settle")
        return None

    def _point_at(self, el) -> None:
        """Rest the mouse on the number and slide along its digits, like reading it off the page."""
        ctx = self.ctx
        y = (el.top + el.bottom) / 2 + ctx.rng.uniform(-2, 2)
        ctx.mouse.move(el.left + 3, y)
        steps = ctx.rng.randint(5, 9)
        for i in range(1, steps + 1):
            ctx.backend.move_to(el.left + 3 + (el.right - el.left - 6) * i / steps, y + ctx.rng.uniform(-1, 1))
            ctx.pacer.tiny(ctx.rng.uniform(0.04, 0.12))
        ctx.pacer.wait("read")

    def save(self) -> None:
        if self.window and self.window.app == "calc":
            names = self.item.spec.get("file") or ["crypto prices {date}"]
            self.day.desk.save(self.window, name=self.day.fill(self.ctx.rng.choice(names)))


class LaptopCompare(Task):
    """Hybrid: Dell homepage, find the 'Laptops' link and click it. On the mock range every sub page
    is a 404 (organiser, 11 Oct): the bot sees the error, refreshes once, goes back, tries one other
    laptop link, and writes down what happened."""
    kind = "hybrid"

    def steps(self):
        rng, url = self.ctx.rng, self.item.spec["site"]
        if not self.browse_to(url):
            self.status, self.note = "failed", self.say("site_error", site="dell")
            return
        self.skill("scroll_and_read", {"bursts_range": [2, 4]})
        if rng.random() < 0.6: self.skill("hover_nav", {})
        yield "read"
        laptop_links = self.scan_for(lambda els: [l for l in E.links(els, ["laptop"]) if "laptop" in l.name.lower()]) or []
        page = []
        for link in laptop_links[:2]:                      # the Laptops link, then one other
            page = self.click_link(link)
            if page: break
        if not page:
            self.status = "failed"
            self.note = ", " + rng.choice(["dell laptop pages error, try later", "laptop pages not opening, try later"])
            return
        self.status, self.note = "done", ", " + rng.choice(["had a look, ask sales for prices", "looked, no prices online"])


class WriterNote(Task):
    """Office: a new Writer document, a short note composed the messy way, saved."""
    kind = "office"

    def steps(self):
        day, rng, ctx = self.day, self.ctx.rng, self.ctx
        if self.item.spec.get("note") == "linked":          # grows out of the day's hybrid task
            title, sentences, extras = linked_note(rng, self.item.spec.get("_link"), self.item.label)
        else:
            title, sentences, extras = note_sentences(rng, self.item.spec.get("note", "meeting"), self.item.label)
        self.title = title
        win = day.desk.new_document("writer", self.item.label)
        self.window = win
        doc = WriterDoc(ctx, name=title)
        win.doc = doc
        day.mark_app("writer")
        ctx.pacer.wait("settle")
        day.desk.ensure_front(win, "note title")
        Composer(doc, rng, day.wait).write([Unit(title, newline_after=2, can_park=False)])
        win.dirty = True
        yield "title"
        split = rng.randint(1, max(1, len(sentences) - 1))
        paragraphs = [sentences[:split], sentences[split:]] if len(sentences) > 2 and rng.random() < 0.6 else [sentences]
        for p, para in enumerate(paragraphs):
            units = [Unit(s, a) for s, a in para]
            if p < len(paragraphs) - 1: units[-1].newline_after = 2
            for k in range(0, len(units), 3):            # a safe point every three sentences
                day.desk.ensure_front(win, "note")
                chunk = units[k:k + 3]
                if k + 3 < len(units) and not chunk[-1].newline_after:
                    chunk[-1] = Unit(chunk[-1].text, chunk[-1].alt, 0, chunk[-1].can_park)
                    Composer(doc, rng, day.wait, extras=extras).write(chunk)
                    doc.type(" ")                        # the space before the next sentence
                else:
                    Composer(doc, rng, day.wait, extras=extras).write(chunk)
                win.dirty = True
                if k + 3 < len(units) or p < len(paragraphs) - 1: yield "sentences"
        yield "written"
        if rng.random() < 0.3:
            day.desk.ensure_front(win, "title style")
            self.skill("emphasize_title", {})
            doc.cur = len(doc.text)
        self.save()
        self.status = "done"
        self.note = ", " + rng.choice(SAVED_NOTE).format(file=win.file)

    def save(self) -> None:
        if self.window is not None:
            self.day.desk.save(self.window, name=self.day.fill(getattr(self, "title", "notes {date}")))


class SheetTask(Task):
    """Office: Calc only. A new sheet, or more rows on the same kind of sheet opened earlier today."""
    kind = "office"

    def steps(self):
        day, rng, ctx = self.day, self.ctx.rng, self.ctx
        kind = self.item.spec.get("sheet", "budget")
        win = day.reuse_window(kind)
        if win:
            day.desk.focus(win, kind); sheet = win.doc
            sheet.go_next_free_row()
        else:
            headers, _ = sheet_rows(rng, kind, 0)
            win = day.desk.new_document("calc", kind + " sheet")
            win.extra["topic"] = kind
            sheet = CalcSheet(ctx, headers, sum_cols=[2])
            win.doc = sheet
            day.desk.ensure_front(win, "sheet")
            sheet.start()
        self.window = win
        day.mark_app("calc")
        _, rows = sheet_rows(rng, kind, rng.randint(*P("task.rows_to_add")), used={r[0] if kind == "budget" else r[1] for r in sheet.rows})
        for n, row in enumerate(rows):
            day.desk.ensure_front(win, "row")
            sheet.add_row(row)
            win.dirty = True
            if n < len(rows) - 1 and n % 2 == 1: yield "rows"
        sheet.total()
        self.save()
        self.status = "done"
        self.note = ", " + rng.choice(SAVED_NOTE).format(file=win.file)

    def save(self) -> None:
        if self.window is not None:
            names = self.item.spec.get("file") or ["sheet {date}"]
            self.day.desk.save(self.window, name=self.day.fill(self.ctx.rng.choice(names)))


class CryptoCompare(Task):
    """Hybrid over two sites: the US$ price read on CoinGecko, the S$ price read on Coinbase, then a
    Calc sheet with both and a formula for the rate (S$ / US$). Everything comes off the pages.

    Keeps what it has (design 25 Oct): when Coinbase shows no prices (VM 25 Oct) or is down, the sheet
    is still made with the US$ prices, SGD and rate left empty, saved, and the line ends "started".
    Picked up again later, it looks at Coinbase once more and fills the gaps if prices are there."""
    kind = "hybrid"

    def steps(self):
        day, rng, ctx = self.day, self.ctx.rng, self.ctx
        if self.item.spec.get("_fx_pending") and day.reuse_window("fx") is not None:
            yield from self._fill_later(); return
        self.item.spec["_fx_started_at"] = day.now()
        page = self.browse_to("https://coingecko.com")
        coins_usd = E.coingecko_coins(page) if page else []
        if page and not coins_usd:
            coins_usd = self.look_again_for(E.coingecko_coins, "Bitcoin") or []
        if not coins_usd:
            self.rec("missing", site="coingecko", thing="prices") if page else None
            self.status = "failed"
            self.note = self.say("site_error", site="coingecko") if self.site_failed() else self.say("missing", site="coingecko", what="prices")
            return
        usd = {c["name"]: c["price"] for c in coins_usd}
        self.skill("scroll_and_read", {"bursts_range": [1, 3]})
        yield "read usd"
        page = self.browse_to("https://www.coinbase.com", new_tab=True)
        sgd = {}
        if page:
            got = E.coinbase_coins(page) or self.look_again_for(E.coinbase_coins, "Bitcoin") or []
            sgd = {c["name"]: c["price_sgd"] for c in got}
            if not sgd: self.rec("missing", site="coinbase", thing="prices")
        both = [n for n in sgd if n in usd and n not in ("USDC",)]
        pool = both or [n for n in usd if n not in ("USDC", "USDS", "Tether")]
        focus = (self.item.spec.get("_coin") or "").title()
        others = [n for n in pool if n != focus]
        coins = ([focus] if focus in pool else []) + rng.sample(others, min(2, len(others)))
        yield "read sgd"
        browser = self.window
        win = day.desk.new_document("calc", "crypto usd vs sgd")
        win.extra["topic"] = "fx"
        sheet = CalcSheet(ctx, ["Coin", "USD", "SGD", "Rate"], sum_cols=[])
        win.doc = sheet
        self.window = win
        self.split_screen(browser, win)
        day.desk.ensure_front(win, "sheet")
        day.mark_app("calc")
        sheet.start()
        for n, coin in enumerate(coins):
            row = len(sheet.rows) + 2
            day.desk.ensure_front(win, "row")
            if coin in sgd:
                sheet.add_cells([coin, self._look_type(browser, win, coin, usd[coin], "coingecko"),
                                 self._look_type(browser, win, coin, sgd[coin], "coinbase"), f"=C{row}/B{row}"])
            else:                                          # no S$ price to be had: leave it for later
                sheet.add_cells([coin, self._look_type(browser, win, coin, usd[coin], "coingecko", one_tab=not both)])
            win.dirty = True
            if n < len(coins) - 1:
                self.next_need_s = P("task.row_need_s"); yield "row"; self.next_need_s = 0.0
        self.save()
        self.item.found = {"kind": "fx", "file": win.file, "facts": [(c, usd[c], sgd.get(c)) for c in coins]}
        if both:
            rate = float(sgd[coins[0]]) / float(usd[coins[0]])
            self.status = "done"
            self.note = f", rate about {rate:.2f}, " + rng.choice(SAVED_NOTE).format(file=win.file)
        else:
            self.status = "started"                          # kept what it had; the rest is missing
            self.item.spec["_fx_pending"] = coins
            self.item.resume = True
            self.note = self.say("missing_started", site="coinbase", what="sgd prices", file=win.file)

    def _fill_later(self):
        """Coming back to the sheet later: look at Coinbase again; if the prices are there now, fill in
        SGD and the rate for the coins already on the sheet."""
        day, rng, ctx = self.day, self.ctx.rng, self.ctx
        win = day.reuse_window("fx")
        coins = self.item.spec["_fx_pending"]
        page = self.browse_to("https://www.coinbase.com")
        got = (E.coinbase_coins(page) or self.look_again_for(E.coinbase_coins, "Bitcoin") or []) if page else []
        sgd = {c["name"]: c["price_sgd"] for c in got}
        yield "looked again"
        if not any(c in sgd for c in coins):
            self.rec("missing", site="coinbase", thing="prices")
            self.status = "started"
            self.note = ""                                   # the line already says so: nothing new to write
            self.item.resume = False                         # one look again is enough for today
            return
        browser = self.window
        self.window = win
        day.desk.focus(win, "fill in sgd"); day.mark_app("calc")
        day.desk.ensure_front(win, "fill in sgd")
        sheet = win.doc
        for n, coin in enumerate(coins):
            if coin not in sgd: continue
            sheet.goto(n + 1, 2)                           # the SGD cell of that coin's row
            sheet.fill_from([self._look_type(browser, win, coin, sgd[coin], "coinbase", one_tab=True),
                             f"=C{n + 2}/B{n + 2}"])
            win.dirty = True
        self.save()
        self.item.spec.pop("_fx_pending", None)
        self.status = "done"
        self.note = ", " + rng.choice(["filled in sgd", "sgd added"]) + ", " + rng.choice(SAVED_NOTE).format(file=win.file)

    def _look_type(self, browser, win, coin, value, site, one_tab: bool = False):
        day, ctx = self.day, self.ctx

        def enter():
            day.desk.focus(browser, f"{coin} on {site}"); day.mark_app("browser")
            if site == "coingecko" and not one_tab:         # the CoinGecko tab is the one before
                ctx.backend.hotkey("ctrl", "shift", "tab"); day.eyes.see("https://coingecko.com")
            self.skill("find_on_page", {"text": coin})
            ctx.pacer.wait("read")
            if site == "coingecko" and not one_tab:
                ctx.backend.hotkey("ctrl", "tab"); day.eyes.see("https://www.coinbase.com")
            day.desk.focus(win, "type it"); day.mark_app("calc")
            ctx.typer.type_text(value, ctx="number")
        return enter

    def save(self) -> None:
        if self.window is not None and self.window.app == "calc":
            self.day.desk.save(self.window, name=self.day.fill(self.ctx.rng.choice(["crypto usd sgd {date}", "coin prices sgd {date}"])))


# what a note task says it found none of, when the page gave nothing to write from
MISSING_WHAT = {"phone": "phones", "news": "headlines", "training": "courses", "cloud": "cloud facts", "asana": "useful info"}


class ReadNote(Task):
    """Hybrid: read one or two sites, then a short Writer note built from what the eyes read on
    them just now (news round up, training ideas, cloud comparison, phone options, Asana notes)."""
    kind = "hybrid"

    def steps(self):
        day, rng, ctx = self.day, self.ctx.rng, self.ctx
        facts = {}
        down = []                                          # sites that were an error even after a refresh
        for n, url in enumerate(self.item.spec["sites"]):
            page = self.browse_to(url, new_tab=True if n else None)
            if not page:
                down.append(self.site_name(url))
                continue                                    # keep going with the other site, if any
            self.skill("scroll_and_read", {"bursts_range": [2, 5]})
            if self.item.spec.get("find") and rng.random() < 0.5:
                self.skill("find_on_page", {"text": self.item.spec["find"]})
            # read what the page shows after scrolling, not only the read on arrival: Asana fills in late and
            # the arrival read gave nothing to note (VM run 4, 25 Oct, finding 23); one more look after a wait
            got = self._take_in(url, self.look() or page)
            if not any(any(d.values()) for k, d in got.items() if k != "_els"):
                ctx.pacer.wait("read")
                got = self._take_in(url, self.look() or page)
            els = got.pop("_els", {})
            facts.update(got)
            facts.setdefault("_els", {}).update({k: v for k, v in els.items() if v is not None})
            yield "read " + self.site_name(url)
        made = RECIPES[self.item.spec["recipe"]](rng, facts, self.item.label)
        if made is None:
            self.status = "failed"
            if down: self.note = self.say("site_error", site=down[0])
            else: self.note = self.say("missing", site=self.site_name(self.item.spec["sites"][0]),
                                       what=MISSING_WHAT.get(self.item.spec["recipe"], "useful info"))
            return
        self.title = made["title"]
        self.followup = made.get("followup")
        browser = self.window
        win = day.desk.new_document("writer", self.item.label)
        self.window = win
        doc = WriterDoc(ctx, name=self.title)
        win.doc = doc
        self.split_screen(browser, win)                     # page on the left, the note on the right
        day.mark_app("writer")
        ctx.pacer.wait("settle")
        day.desk.ensure_front(win, "note title")
        Composer(doc, rng, day.wait).write([Unit(self.title, newline_after=2, can_park=False)])
        win.dirty = True
        yield "title"
        dash = day.todo.dash
        # One line per thing taken off the page. Lines that get copied are pasted one by one; the
        # typed ones are written together with the closing line, so blocking and rewrites can happen
        # across them (a later line typed too early, cut, parked, moved back).
        pending = []
        for n, item in enumerate(made["items"]):
            el = facts.get("_els", {}).get(item["copy"])
            if el is not None and self._wants_copy(item, el):
                if pending:
                    day.desk.ensure_front(win, "note lines")
                    Composer(doc, rng, day.wait).write(pending); pending = []
                    win.dirty = True
                    yield "items"
                if not self._copy_item(browser, win, doc, item, el, dash):
                    pending.append(Unit(dash + item["text"], newline_after=1))
                win.dirty = True
            else:
                pending.append(Unit(dash + item["text"], newline_after=1))
        units = pending + [Unit(a, b) for a, b in made["outro"]]
        if units:
            # no stop inside one write: say how long it needs, so the end of day check can cut here
            self.next_need_s = P("task.write_s_per_char") * sum(len(u.text) for u in units) + 15
            yield "before writing"
            self.next_need_s = 0.0
            if browser in day.desk.mru and rng.random() < 0.6:
                self._glance(browser, win, units[0].text)     # look the items up on the page first
            day.desk.ensure_front(win, "note")
            Composer(doc, rng, day.wait, extras=made.get("extras")).write(units)
            win.dirty = True
        self.save()
        self.item.found = {"kind": self.item.spec.get("recipe", ""), "file": win.file,
                           "facts": [i["text"] for i in made["items"]]}
        self.status = "done"
        self.note = (self.say("one_site_error", site=down[0]) if down else "") + ", " + rng.choice(SAVED_NOTE).format(file=win.file)
        if made.get("partial"):                              # less than the line asked for: say what was there
            self.status, self.note = "started", ", " + made["partial"]

    def _wants_copy(self, item, el) -> bool:
        lists = self.day.cfg.get("lists") or {}
        if str(lists.get("copy", "off")).lower() not in ("on", "true"): return False
        if lists.get("copy_check", "whole") == "whole" and el.name != item["copy"]: return False
        return self.ctx.rng.random() < P("copy.notes_p")

    def _copy_item(self, browser, win, doc, item, el, dash) -> bool:
        """Copy one item off the page into the note: select it with the mouse, Ctrl+C (often twice),
        back to Writer, paste as plain text, fix what the rough selection got wrong ("cleaning").
        Off unless lists.copy is on (needs the VM check of Ctrl+Alt+Shift+V)."""
        day, ctx, rng = self.day, self.ctx, self.ctx.rng
        lists = day.cfg.get("lists") or {}
        wanted, mode = item["copy"], lists.get("copy_check", "whole")
        whole = el.name == wanted
        if mode == "whole" and not whole: return False
        if el.kind == "hyperlink": return False             # a drag on a link opens it (VM 25 Oct, finding 1)
        day.desk.focus(browser, "copy " + wanted[:20]); day.mark_app("browser")
        start = el.name.find(wanted)
        if mode == "whole":
            self.copy_from_page(el)
            got = wanted
        else:
            miss_a = rng.choice([0, 0, 0, -1, 1]); miss_b = rng.choice([0, 0, 0, -1, 1])
            a, b = max(0, start + miss_a), min(len(el.name), start + len(wanted) + miss_b)
            cw = el.width / max(1, len(el.name))
            part = type(el)(el.name[a:b], int(el.left + a * cw), el.top, int(el.left + b * cw), el.bottom, el.kind)
            self.copy_from_page(part)
            got = day.desk.clipboard_text() if getattr(day.eyes, "uia", None) else el.name[a:b]
            if not got or len(got) > len(wanted) + 6:      # copied something else: type it instead
                day.desk.focus(win, "type it"); return False
        day.desk.focus(win, "paste"); day.mark_app("writer")
        day.desk.ensure_front(win, "paste")
        if item.get("prefix"): doc.type(dash + item["prefix"])
        elif dash: doc.type(dash)
        ctx.backend.hotkey("ctrl", "alt", "shift", "v")     # paste unformatted text
        doc._insert(got)
        ctx.pacer.wait("read")
        if got != wanted:                                  # the rough selection was off: clean it up
            line_start = doc.cur - len(got)
            target = doc.text[:line_start] + wanted + doc.text[doc.cur:]
            doc.clean_to(target)
            doc.go(line_start + len(wanted))
            day.log({"event": "cleaned_paste", "got": got, "wanted": wanted})
        doc.enter()
        day.log({"event": "copied_line", "text": wanted[:40]})
        return True

    def _glance(self, browser, win, sentence: str) -> None:
        """Switch to the page, find the words about to be written (Ctrl+F), read, switch back."""
        day, ctx = self.day, self.ctx
        words = [w.strip(".,:?") for w in sentence.split() if len(w.strip(".,:?")) > 4][:3]
        day.desk.focus(browser, "look it up"); day.mark_app("browser")
        title = day.desk.title().lower().replace(" ", "")
        sites = [self.site_name(u) for u in self.item.spec.get("sites", [])]
        if title and sites and not any(s in title for s in sites):
            words = []                                     # not the task's page in front: no search here
            day.log({"event": "glance_skipped", "title": title[:40]})
        if words: self.skill("find_on_page", {"text": " ".join(words[-2:])})
        ctx.pacer.wait("read")
        day.desk.focus(win, "back to the note"); day.mark_app("writer")

    @staticmethod
    def _take_in(url: str, page) -> dict:
        """What a person would take in from each page, read just now."""
        if "apnews" in url or "bbc" in url:
            hs = E.headlines(page)
            return {("apnews" if "apnews" in url else "bbc"): {"headlines": [h.name for h in hs]}, "_els": {h.name: h for h in hs}}
        if "coursera" in url:
            offer = next((e.name.rstrip(".") for e in page if "save" in e.name.lower() and "%" in e.name and len(e.name) < 90), "")
            names = E.courses(page)
            wanted = set(names)
            els = {e.name: e for e in page if e.name in wanted}
            return {"coursera": {"courses": names, "offer": offer[:1].lower() + offer[1:]}, "_els": els}
        if "samsung" in url:
            # phones only: earbuds, tablets and watches are not "phone options" (Kellyn, 25 Oct)
            models = [m for m in E.galaxy_models(page) if m.startswith(("Galaxy Z", "Galaxy S", "Galaxy A"))]
            pre = any("pre-registration" in e.name.lower() for e in E.content(page))
            return {"samsung": {"models": models, "pre_registration": pre},
                    "_els": {m: next((e for e in page if m in e.name and e.kind == "hyperlink"), None) for m in models}}
        if "aws" in url:
            pts = [re.split(r",| with announced", t)[0] for t in E.fact_lines(page) if len(t.split()) >= 4]
            return {"aws": {"points": [p for p in pts if any(c.isdigit() for c in p)][:4]}}
        if "cloud.google" in url:
            return {"googlecloud": {"points": [re.sub(r"^Start now with ", "", t) for t in E.fact_lines(page, r"\d|free")][:4]}}
        if "asana" in url:
            return {"asana": {"points": [t.rstrip("¹®").strip() for t in E.short_points(page)][:6]}}
        return {}

    def save(self) -> None:
        if self.window is not None and self.window.app == "writer":
            self.day.desk.save(self.window, name=self.day.fill(getattr(self, "title", "notes {date}")))


class TidyFiles(Task):
    """Explorer: look at the Documents folder (eyes read the file list), make a folder, select 2 or
    3 of the bot's own older files with the mouse (Ctrl+click), cut them, open the folder, paste.
    Files that are open right now are left alone. Fewer than 2 files: it only looks."""
    kind = "explorer"
    resumable = False

    def steps(self):
        day, rng, ctx = self.day, self.ctx.rng, self.ctx
        win = day.desk.explorer()
        self.window = win
        day.mark_app("explorer")
        self.skill("explorer_navigate", {"path": "%USERPROFILE%\\" + day.cfg["files"]["work_folder"]})
        if not getattr(day.eyes, "uia", None):
            day.eyes.dialog_items = ["To do"] + day.older_files
        items = day.eyes.read(["Documents", "File Explorer"], kinds=("listitem",), visible=True)
        busy = {w.file for w in day.desk.mru}
        files = [e for e in items if e.name not in ("To do",) and e.name.split(".")[0] not in busy
                 and not e.name.lower().startswith(("todo", "to do", "desktop.ini"))]
        self.skill("browse_items", {"steps_range": [2, 4]})
        yield "look"
        if len(files) < 2:
            self.status, self.note = "done", ", " + rng.choice(["nothing much to tidy", "looked, ok for now"])
            return
        folder = rng.choice(["old notes", "oct work", "archive " + today("{mon}"), "done stuff"])
        picked = rng.sample(files, min(len(files), rng.randint(*P("task.files_to_tidy"))))
        day.desk.ensure_front(win, "tidy")
        for i, el in enumerate(picked):                     # click the first, Ctrl+click the rest
            if i: ctx.backend.key_event("ctrl", True)
            day.desk.click_el(el)
            if i: ctx.backend.key_event("ctrl", False)
            ctx.pacer.wait("step")
        ctx.backend.hotkey("ctrl", "x")
        ctx.pacer.wait("think")
        day.desk.ensure_front(win, "new folder")
        ctx.backend.hotkey("ctrl", "shift", "n")            # new folder, name box open
        ctx.pacer.wait("settle")
        ctx.typer.type_text(folder, ctx="filename")
        ctx.backend.press("enter")
        ctx.pacer.wait("step")
        ctx.backend.press("enter")                          # open the new (selected) folder
        ctx.pacer.wait("settle")
        ctx.backend.hotkey("ctrl", "v")
        ctx.pacer.wait("read")
        ctx.backend.hotkey("alt", "up")                     # back to Documents
        ctx.pacer.wait("settle")
        day.moved_files += [e.name for e in picked]
        self.status = "done"
        self.note = f", moved {len(picked)} files to {folder}"


TASKS = {"crypto_compare": CryptoCompare, "read_note": ReadNote, "browse": Browse, "crypto_prices": CryptoPrices,
         "laptop_compare": LaptopCompare, "writer_note": WriterNote, "calc_sheet": SheetTask, "tidy_files": TidyFiles}
