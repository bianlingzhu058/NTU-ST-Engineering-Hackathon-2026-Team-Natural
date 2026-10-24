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
from .content import RECIPES, SAVED_NOTE, note_sentences, sheet_rows, today
from .doc import Composer, Unit, WriterDoc
from .todo import CalcSheet

ERROR_TITLES = ["404", "not found", "can't reach", "cannot", "error", "isn't available", "problem loading"]


class Task:
    kind = ""
    resumable = True

    def __init__(self, day, item):
        self.day, self.item, self.ctx = day, item, day.ctx
        self.window = None
        self.status, self.note = "open", ""
        self.gen = None
        self.started_at = None

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
        """Open the site in the browser: a new tab most of the time when a page is already open."""
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
        return self.page_ok(url)

    def page_ok(self, url: str) -> bool:
        """A blank or error page: wait, maybe move the mouse, maybe reload once, give up after
        about 20 s (report). Only the window title is checked, never the screen."""
        sensor, ctx = self.ctx.sensor, self.ctx
        if sensor is None or not getattr(sensor, "available", False):
            return not self.day.sim_page_fails(url)
        waited, reloaded = 0.0, False
        while waited < P("task.page_give_up_s"):
            title = (sensor.foreground_title() or "").lower()
            if title and not any(e in title for e in ERROR_TITLES) and "edge" in title and title.split(" - ")[0].strip():
                return True
            ctx.pacer.wait("page_load"); waited += 3.0
            if ctx.rng.random() < 0.4: ctx.mouse.drift()
            if not reloaded and waited > 8 and ctx.rng.random() < P("task.reload_p"):
                ctx.backend.press("f5"); reloaded = True
        return False

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
    """Websurf: open the site, scroll, read, find a word, follow a link or two and come back."""
    kind = "websurf"
    resumable = False

    def steps(self):
        spec, rng = self.item.spec, self.ctx.rng
        url = spec["site"]
        if not self.browse_to(url):
            self.status, self.note = "failed", rng.choice(self.day.fail_notes).format(site=self.site_name(url))
            return
        self.skill("scroll_and_read", {"bursts_range": [2, 5]})
        yield "read"
        if rng.random() < 0.4: self.skill("hover_nav", {})
        if spec.get("find") and rng.random() < 0.5: self.skill("find_on_page", {"text": spec["find"]})
        looks = rng.randint(*P("task.courses_to_look"))
        for n in range(looks):
            self.skill("follow_link", {"tabs_range": [4, 14], "back_probability": 1.0})
            if n < looks - 1:
                self.skill("scroll_and_read", {"bursts_range": [1, 3]})
                yield "link"
        self.maybe_trim_tabs()
        self.status = "done"
        self.note = rng.choice(["", "", ", looked at a few", ", had a look"])


class CryptoPrices(Task):
    """Hybrid: read coin prices on CoinGecko, type 2 to 4 coins (name, price, market cap) and a SUM
    into Calc, save. Numbers are what the page shows (page facts)."""
    kind = "hybrid"

    def steps(self):
        day, rng, ctx = self.day, self.ctx.rng, self.ctx
        coins = [c for c in day.facts["coingecko"]["coins"] if "_" not in c["symbol"]]
        focus = self.item.spec.get("_coin")
        first = [c for c in coins if c["name"].lower() == focus] if focus else []
        others = [c for c in coins if c not in first]
        k = rng.randint(*P("task.coins_to_record"))
        chosen = first + rng.sample(others[:8], k - len(first))
        url = self.item.spec["site"]
        if not self.browse_to(url):
            self.status, self.note = "failed", rng.choice(day.fail_notes).format(site="coingecko")
            return
        self.skill("scroll_and_read", {"bursts_range": [1, 3]})
        if rng.random() < 0.7: self.skill("find_on_page", {"text": chosen[0]["name"]})
        yield "read prices"
        sheet_win = day.reuse_window("crypto")
        if sheet_win:
            day.desk.focus(sheet_win, "crypto sheet"); sheet = sheet_win.doc
            sheet.go_next_free_row()
        else:
            sheet_win = day.desk.new_document("calc", "crypto sheet")
            sheet_win.extra["topic"] = "crypto"
            sheet = CalcSheet(ctx, ["Coin", "Price", "Market cap"], sum_cols=[2])
            sheet_win.doc = sheet
            sheet.start()
        self.window = sheet_win
        day.mark_app("calc")
        for n, coin in enumerate(chosen):
            sheet.add_row([coin["name"], coin["price"], coin["market_cap"]])
            sheet_win.dirty = True
            if n < len(chosen) - 1:
                if rng.random() < 0.3:                       # glance back at the page for the next number
                    browser = day.desk.find("browser")
                    if browser:
                        day.desk.focus(browser[0], "check the price again"); day.mark_app("browser")
                        self.skill("scroll_and_read", {"bursts_range": [1, 2]})
                        day.desk.focus(sheet_win, "back to the sheet"); day.mark_app("calc")
                yield "row"
        sheet.total()
        self.save()
        self.status = "done"
        self.note = ", " + rng.choice(SAVED_NOTE).format(file=sheet_win.file)

    def save(self) -> None:
        if self.window and self.window.app == "calc":
            names = self.item.spec.get("file") or ["crypto prices {date}"]
            self.day.desk.save(self.window, name=self.day.fill(self.ctx.rng.choice(names)))


class LaptopCompare(Task):
    """Hybrid: Dell homepage, look at the laptops, try to open the laptop page. On the mock range
    every sub page is a 404 (organiser, 11 Oct), so this usually ends as an honest failure."""
    kind = "hybrid"

    def steps(self):
        rng, url = self.ctx.rng, self.item.spec["site"]
        if not self.browse_to(url):
            self.status, self.note = "failed", ", " + rng.choice(self.day.fail_notes).format(site="dell")
            return
        self.skill("scroll_and_read", {"bursts_range": [2, 4]})
        if rng.random() < 0.6: self.skill("hover_nav", {})
        yield "read"
        self.skill("follow_link", {"tabs_range": [6, 16], "back_probability": 1.0})
        if not self.page_ok(url + "/laptops"):
            self.status = "failed"
            self.note = ", " + rng.choice(["dell laptop page down, try later", "laptop page not loading, try later"])
            return
        self.status, self.note = "done", ", " + rng.choice(["had a look, ask sales for prices", "looked, no prices online"])


class WriterNote(Task):
    """Office: a new Writer document, a short note composed the messy way, saved."""
    kind = "office"

    def steps(self):
        day, rng, ctx = self.day, self.ctx.rng, self.ctx
        title, sentences, extras = note_sentences(rng, self.item.spec.get("note", "meeting"), self.item.label)
        self.title = title
        win = day.desk.new_document("writer", self.item.label)
        self.window = win
        doc = WriterDoc(ctx, name=title)
        win.doc = doc
        day.mark_app("writer")
        ctx.pacer.wait("settle")
        Composer(doc, rng, day.wait).write([Unit(title, newline_after=2, can_park=False)])
        win.dirty = True
        yield "title"
        split = rng.randint(1, max(1, len(sentences) - 1))
        paragraphs = [sentences[:split], sentences[split:]] if len(sentences) > 2 and rng.random() < 0.6 else [sentences]
        for p, para in enumerate(paragraphs):
            units = [Unit(s, a) for s, a in para]
            if p < len(paragraphs) - 1: units[-1].newline_after = 2
            for k in range(0, len(units), 2):            # a safe point every couple of sentences
                chunk = units[k:k + 2]
                if k + 2 < len(units) and not chunk[-1].newline_after:
                    chunk[-1] = Unit(chunk[-1].text, chunk[-1].alt, 0, chunk[-1].can_park)
                    Composer(doc, rng, day.wait, extras=extras).write(chunk)
                    doc.type(" ")                        # the space before the next sentence
                else:
                    Composer(doc, rng, day.wait, extras=extras).write(chunk)
                win.dirty = True
                if k + 2 < len(units) or p < len(paragraphs) - 1: yield "sentences"
        yield "written"
        if rng.random() < 0.3:
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
            sheet.start()
        self.window = win
        day.mark_app("calc")
        _, rows = sheet_rows(rng, kind, rng.randint(*P("task.rows_to_add")), used={r[0] if kind == "budget" else r[1] for r in sheet.rows})
        for n, row in enumerate(rows):
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


class TidyFiles(Task):
    """Explorer: make a folder in Documents and move 2 or 3 of today's files into it, or rename
    one. Only the bot's own files from today, picked by typing their names (Explorer type-ahead).
    With fewer than 2 files it just looks through the folders."""
    kind = "explorer"
    resumable = False

    def steps(self):
        day, rng, ctx = self.day, self.ctx.rng, self.ctx
        files = [w for w in day.saved_work_files()]
        win = day.desk.explorer()
        self.window = win
        day.mark_app("explorer")
        self.skill("explorer_navigate", {"path": "%USERPROFILE%\\" + day.cfg["files"]["work_folder"]})
        self.skill("browse_items", {"steps_range": [2, 5]})
        yield "look"
        if len(files) < 2:
            self.status, self.note = "done", ", " + rng.choice(["nothing much to tidy", "looked, ok for now"])
            return
        folder = rng.choice(["old notes", "oct work", "archive " + today("{mon}"), "done stuff"])
        ctx.pacer.wait("think")
        ctx.backend.hotkey("ctrl", "shift", "n")         # new folder, name box open
        ctx.pacer.wait("settle")
        ctx.typer.type_text(folder, ctx="filename")
        ctx.backend.press("enter")
        ctx.pacer.wait("read")
        moved = rng.sample(files, min(len(files), rng.randint(*P("task.files_to_tidy"))))
        for name in moved:
            ctx.pacer.wait("think")
            ctx.typer.type_text(name, ctx="noslip")      # type-ahead selects the file
            ctx.pacer.wait("step")
            ctx.backend.hotkey("ctrl", "x")
            ctx.pacer.wait("step")
            ctx.typer.type_text(folder, ctx="noslip")    # select the new folder
            ctx.pacer.wait("step")
            ctx.backend.press("enter")                   # open it
            ctx.pacer.wait("settle")
            ctx.backend.hotkey("ctrl", "v")
            ctx.pacer.wait("read")
            ctx.backend.hotkey("alt", "up")              # back to Documents
            ctx.pacer.wait("settle")
            day.moved_files.append(name)
        self.status = "done"
        self.note = f", moved {len(moved)} files to {folder}"


class CryptoCompare(Task):
    """Hybrid over two sites: the US$ price on CoinGecko, the S$ price on Coinbase, then a Calc
    sheet with both and a formula for the rate (S$ / US$). The numbers are what the pages show."""
    kind = "hybrid"

    def steps(self):
        day, rng, ctx = self.day, self.ctx.rng, self.ctx
        usd = {c["name"]: c["price"] for c in day.facts["coingecko"]["coins"]}
        sgd = {c["name"]: c["price_sgd"] for c in day.facts["coinbase"]["coins"]}
        both = [n for n in sgd if n in usd and n not in ("USDC",)]
        focus = (self.item.spec.get("_coin") or "").title()
        coins = ([focus] if focus in both else []) + rng.sample([n for n in both if n != focus], rng.randint(1, 2))
        if not self.browse_to("https://coingecko.com"):
            self.status, self.note = "failed", rng.choice(day.fail_notes).format(site="coingecko"); return
        self.skill("scroll_and_read", {"bursts_range": [1, 3]})
        self.skill("find_on_page", {"text": coins[0]})
        yield "read usd"
        if not self.browse_to("https://www.coinbase.com", new_tab=True):
            self.status, self.note = "failed", rng.choice(day.fail_notes).format(site="coinbase"); return
        self.skill("scroll_and_read", {"bursts_range": [2, 4]})
        if rng.random() < 0.6: self.skill("find_on_page", {"text": coins[0]})
        yield "read sgd"
        win = day.desk.new_document("calc", "crypto usd vs sgd")
        win.extra["topic"] = "fx"
        sheet = CalcSheet(ctx, ["Coin", "USD", "SGD", "Rate"], sum_cols=[])
        win.doc = sheet
        self.window = win
        day.mark_app("calc")
        sheet.start()
        for n, coin in enumerate(coins):
            row = len(sheet.rows) + 2
            sheet.add_row([coin, usd[coin], sgd[coin], f"=C{row}/B{row}"])
            win.dirty = True
            if n < len(coins) - 1:
                if rng.random() < 0.4:                       # look back at the page for the next price
                    browser = day.desk.find("browser")
                    if browser:
                        day.desk.focus(browser[0], "check the next price"); day.mark_app("browser")
                        self.skill("scroll_and_read", {"bursts_range": [1, 2]})
                        day.desk.focus(win, "back to the sheet"); day.mark_app("calc")
                yield "row"
        self.save()
        rate = float(sgd[coins[0]]) / float(usd[coins[0]])
        self.status = "done"
        self.note = f", rate about {rate:.2f}, " + rng.choice(SAVED_NOTE).format(file=win.file)

    def save(self) -> None:
        if self.window is not None and self.window.app == "calc":
            self.day.desk.save(self.window, name=self.day.fill(self.ctx.rng.choice(["crypto usd sgd {date}", "coin prices sgd {date}"])))


class ReadNote(Task):
    """Hybrid: read one or two sites, then a short Writer note built from what they show
    (news round up, training ideas, cloud comparison, phone options, Asana notes)."""
    kind = "hybrid"

    def steps(self):
        day, rng, ctx = self.day, self.ctx.rng, self.ctx
        sites = self.item.spec["sites"]
        for n, url in enumerate(sites):
            if not self.browse_to(url, new_tab=True if n else None):
                self.status = "failed"
                self.note = ", " + rng.choice(day.fail_notes).format(site=self.site_name(url))
                return
            self.skill("scroll_and_read", {"bursts_range": [2, 5]})
            if self.item.spec.get("find") and rng.random() < 0.5:
                self.skill("find_on_page", {"text": self.item.spec["find"]})
            yield "read " + self.site_name(url)
        title, sentences, extras = RECIPES[self.item.spec["recipe"]](rng, day.facts, self.item.label)
        self.title = title
        win = day.desk.new_document("writer", self.item.label)
        self.window = win
        doc = WriterDoc(ctx, name=title)
        win.doc = doc
        day.mark_app("writer")
        ctx.pacer.wait("settle")
        Composer(doc, rng, day.wait).write([Unit(title, newline_after=2, can_park=False)])
        win.dirty = True
        yield "title"
        units = [Unit(a, b) for a, b in sentences]
        for k in range(0, len(units), 2):
            chunk = units[k:k + 2]
            Composer(doc, rng, day.wait, extras=extras).write(chunk)
            if k + 2 < len(units): doc.type(" ")
            win.dirty = True
            if k + 2 < len(units): yield "sentences"
        self.save()
        self.status = "done"
        self.note = ", " + rng.choice(SAVED_NOTE).format(file=win.file)

    def save(self) -> None:
        if self.window is not None and self.window.app == "writer":
            self.day.desk.save(self.window, name=self.day.fill(getattr(self, "title", "notes {date}")))


TASKS = {"crypto_compare": CryptoCompare, "read_note": ReadNote, "browse": Browse, "crypto_prices": CryptoPrices, "laptop_compare": LaptopCompare,
         "writer_note": WriterNote, "calc_sheet": SheetTask, "tidy_files": TidyFiles}
