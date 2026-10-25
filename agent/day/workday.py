"""One simulated person's work session, from the to do list to closing every app.

Start: the run length is set before Start (3 min to 9 h); nobody touches the bot after that.
The bot writes its own dated to do list in Writer (items drawn at random each run, worded
casually), saves it in Documents\\To do, and keeps it open all day.

During: one task at a time, usually in list order. Between tasks it may glance at the list,
cross off what it finished (now or at a later visit), write failures down honestly, add items
when the list runs low or after lunch, and delete an item that turned out unnecessary. Breaks
(away, on a personal site, lunch on long runs) come between tasks or cut into one. A cut office
or hybrid task is picked up again later about 3 times in 4 (Mark 2005: 77%).

End: open items get ", tbc" (typed once, copied to the rest), started ones ", started, tbc", a
progress line on runs over 5 min; everything is saved and every app is closed.
"""
import collections
import os
from pathlib import Path
from ..behaviour.dist import clamp, ln_median
from ..behaviour.params import P
from ..config import yaml
from .content import FAIL_NOTES, PEOPLE, TEAMS, DONE_NOTES, today
from .desk import Desk
from .tasks import TASKS
from .todo import Item, TodoList

COIN_LABELS = ["bitcoin", "ethereum", "solana", "dogecoin", "xrp"]


class Cut(Exception):
    def __init__(self, why: str):
        super().__init__(why); self.why = why


class Workday:
    def __init__(self, context, root: Path, minutes: float, sim: bool = False, first_run: bool = False):
        self.ctx, self.root, self.minutes, self.sim = context, root, float(minutes), sim
        self.first_run = first_run
        self.rng = context.rng
        self.cfg = yaml.safe_load((root / "config" / "workday.yaml").read_text(encoding="utf-8"))
        from .eyes import Eyes, SimEyes
        self.eyes = SimEyes(root, self.rng) if sim else Eyes()
        context.eyes = self.eyes
        # simulator only: older files from an earlier day, for the tidy up task to find
        self.older_files = ["crypto prices 23 oct", "meeting notes 23 oct", "budget oct", "news notes 23 oct"] if sim else []
        self.log_rows = collections.deque(maxlen=20000)  # for the simulator report; bounded on long runs
        self.desk = Desk(context, self.cfg, self.log)
        self.todo = TodoList(context, self.desk, self.cfg, self.log)
        self.fail_notes = FAIL_NOTES
        self.paused: list = []
        self.pending_followups: list[str] = []
        self.moved_files: list[str] = []
        self.app_time: dict[str, float] = {}
        self._app, self._app_since = "harness", None
        self.breaks: list[dict] = []
        self.compose_reports = []

    # small helpers
    def now(self) -> float:
        return self.ctx.pacer.now()

    def log(self, event: dict) -> None:
        event = {"t": round(self.now() - self.t0, 1) if hasattr(self, "t0") else 0.0, **event}
        self.log_rows.append(event)
        self.ctx.logger.log(event)

    def wait(self, seconds: float) -> None:
        self.ctx.pacer.sleep_for("think_s", seconds)

    def fill(self, text: str) -> str:
        return text.replace("{date}", today()).replace("{mon}", today("{mon}")).replace("{day}", today("{day}"))

    def mark_app(self, app: str) -> None:
        """Bookkeeping for the time split report (share of time per app)."""
        t = self.now()
        if self._app_since is not None:
            self.app_time[self._app] = self.app_time.get(self._app, 0.0) + t - self._app_since
        self._app, self._app_since = app, t

    def stopped(self) -> bool:
        return self.ctx.pacer.stopped()

    def left(self) -> float:
        return self.end - self.now()

    def reserve(self) -> float:
        open_n = sum(1 for i in self.todo.visible() if i.status in ("open", "started"))
        return P("todo.end_reserve_s") + 6 * open_n + 5 * max(0, len(self.desk.mru) - 1)

    def sim_page_fails(self, url: str) -> bool:
        """Laptop simulation only: sub pages of the mock sites are 404 (organiser, 11 Oct)."""
        blocked = ("booking.com", "arstechnica", "aliexpress", "binance", "cloudflare", "coinmarketcap", "bleacherreport")
        return url.rstrip("/").count("/") > 2 or any(b in url for b in blocked)

    def reuse_window(self, topic: str):
        owned = {id(t.window) for t in self.paused}
        for w in self.desk.mru:
            if w.extra.get("topic") == topic and w.doc is not None and id(w) not in owned: return w
        return None

    # planning the list
    def _label(self, spec: dict) -> tuple[str, dict]:
        spec = dict(spec)
        label = self.rng.choice(spec["labels"])
        if isinstance(label, list):                         # [line, word to Ctrl+F, read/open, answer word]
            label, spec["need"], spec["goal"], *rest = label
            spec["answer"] = rest[0] if rest else ""
        if "{coin}" in label:
            spec["_coin"] = self.rng.choice(COIN_LABELS)
            label = label.replace("{coin}", spec["_coin"])
        label = label.replace("{person}", self.rng.choice(PEOPLE)).replace("{team}", self.rng.choice(TEAMS))
        return label, spec

    def _usable(self, spec: dict) -> bool:
        return self.minutes >= spec.get("min_minutes", 0)

    @staticmethod
    def _spec_key(spec: dict) -> str:
        return f'{spec.get("task", "")}:{spec.get("site") or spec.get("recipe") or spec.get("note") or spec.get("sheet") or ""}'

    def draw_items(self, n: int, taken: set[str]) -> list[Item]:
        """n new lines. The same piece of work shows up once a day, except the sheet tasks that a
        person updates again (crypto sheet up to 3 times, other sheets twice)."""
        weights = P("task.weights")
        pool = [s for s in self.cfg["items"] if self._usable(s)]
        on_list = collections.Counter(self._spec_key(i.spec) for i in self.todo.items)
        repeats = {"crypto_prices": 3, "calc_sheet": 2}
        if any(i.spec.get("rare") for i in self.todo.items): pool = [p for p in pool if not p.get("rare")]
        out = []
        for _ in range(n * 6):
            if len(out) >= n: break
            kind = self.rng.choices(list(weights), weights=list(weights.values()), k=1)[0]
            options = [s for s in pool if s["kind"] == kind and (not s.get("rare") or self.rng.random() < 0.15)]
            if not options: continue
            label, spec = self._label(self.rng.choice(options))
            key = self._spec_key(spec)
            if label in taken: continue                      # never two identical lines
            if on_list[key] >= repeats.get(spec["task"], 1): continue
            taken.add(label)
            on_list[key] += 1
            out.append(Item(label, spec))
        if not out and n:
            # Every item has been on today's list (long runs): look at a site or a sheet again,
            # worded as such ("skim ap news again"), instead of sitting idle.
            again = [i for i in self.todo.items if i.spec.get("task") in ("browse", "calc_sheet", "crypto_prices")
                     and i.status in ("done", "failed")]
            self.rng.shuffle(again)
            for old in again:
                for word in (" again", ", round two", " later on"):
                    label = old.label.split(" again")[0].split(", round two")[0].split(" later on")[0] + word
                    if label not in taken and len(label) < 60:
                        taken.add(label); out.append(Item(label, dict(old.spec))); break
                if len(out) >= n: break
        return out

    RELIABLE_HYBRIDS = ("crypto_prices", "crypto_compare", "read_note")   # always end with a sheet or note
    LINKED = {   # an office task that grows out of the hybrid, written from what the hybrid found
        "crypto_prices": ["send crypto summary to {person}", "crypto update for {person}"],
        "crypto_compare": ["send the sgd rates to {person}", "fx note for {person}"],
        "news": ["email the team about the news", "news summary for {person}"],
        "training": ["send course list to {person}", "course options email"],
        "phone": ["message {person} about phones", "phone shortlist for {person}"],
        "cloud": ["cloud summary for IT", "write cloud note for {person}"],
        "asana": ["asana pitch for the team", "asana summary for {person}"],
    }

    def plan(self) -> list[Item]:
        for limit, (lo, hi) in P("todo.items_by_minutes"):
            if self.minutes <= limit: break
        n = self.rng.randint(lo, hi)
        taken: set[str] = set()
        # No line is forced any more (team, 25 Oct: the judges asked for no hardcoding): every line is drawn
        # from the pool by its weight. A short run only gets fewer lines.
        short = self.minutes < P("plan.short_run_minutes")
        items = self.draw_items(2 if short else n, taken)
        if self.minutes >= P("todo.personal_min_minutes"):
            k = self.rng.randint(*P("todo.personal_items"))
            for spec in self.rng.sample(self.cfg["personal"], k):
                label = spec["label"].replace("{person}", self.rng.choice(PEOPLE))
                items.insert(self.rng.randrange(1, len(items) + 1), Item(label, dict(spec), personal=True))
        if self.minutes >= 10:
            for item in items[1:]:
                if not item.personal and self.rng.random() < P("todo.delete_p"):
                    item.delete_at = self.t0 + self.rng.uniform(0.2, 0.9) * self.minutes * 60
        return items

    def plan_breaks(self) -> None:
        self.next_break = None
        self.lunch_at = None
        m = self.minutes
        if m < 10: return
        if m < 60:
            if self.rng.randint(*P("break.fifteen_min_count")):
                self.next_break = self.t0 + self.rng.uniform(0.3, 0.7) * m * 60
            self.short_run_breaks = True
            return
        self.short_run_breaks = False
        self.next_break = self.t0 + self._sitting()
        if m / 60 > P("break.lunch_after_h"):
            self.lunch_at = self.t0 + self.rng.uniform(0.42, 0.55) * m * 60

    def _sitting(self) -> float:
        median, sigma, low, high = P("break.sitting_s")
        return clamp(ln_median(self.rng, median, sigma), low, high)

    # the day
    def run(self) -> dict:
        ctx = self.ctx
        self.t0 = self.now()
        self.end = self.t0 + self.minutes * 60
        self.mark_app("harness")
        self.log({"event": "workday_start", "minutes": self.minutes, "wpm": ctx.typer.wpm})
        items = self.plan()
        self.plan_breaks()
        title = self.fill(self.rng.choice(self.cfg["todo"]["title"]))
        folder = self.ensure_todo_folder()
        self.mark_app("writer")
        report = self.todo.write_new(title, items, self.wait)
        self.compose_reports.append(report)
        self.safely(self.desk.save, self.todo.window, folder, self.fill(self.cfg["todo"]["file"]))
        try:
            self.loop()
        except Cut:
            pass
        self.finish()
        self.mark_app("end")
        return self.summary()

    def ensure_todo_folder(self) -> str:
        folder = self.cfg["files"]["todo_folder"]
        if os.path.isdir(os.path.join(self.desk.profile, folder)) or (self.sim and not self.first_run):
            return folder
        if self.cfg["files"].get("make_folder") != "explorer":
            return self.cfg["files"]["work_folder"]
        parent, name = folder.rsplit("\\", 1)
        win = self.desk.explorer(); self.mark_app("explorer")
        self.desk._skill("explorer_navigate", {"path": "%USERPROFILE%\\" + parent})
        ctx = self.ctx
        ctx.pacer.wait("think")
        try:
            self.desk.ensure_front(win, "make folder")
        except Exception:
            self.log({"event": "folder_missing_fallback", "folder": folder})
            return self.cfg["files"]["work_folder"]
        ctx.backend.hotkey("ctrl", "shift", "n")
        ctx.pacer.wait("settle")
        ctx.typer.type_text(name, ctx="filename")
        ctx.backend.press("enter")
        ctx.pacer.wait("read")
        self.log({"event": "made_folder", "folder": folder})
        if self.sim or os.path.isdir(os.path.join(self.desk.profile, folder)):
            return folder
        self.log({"event": "folder_missing_fallback", "folder": folder})
        return self.cfg["files"]["work_folder"]

    def loop(self) -> None:
        while not self.stopped():
            if self.left() < self.reserve() + 40:
                break
            self.safely(self.maybe_break)
            if self.left() < self.reserve() + 40:
                break
            task = self.pick()
            if task is None:
                if self.minutes < P("plan.short_run_minutes"):
                    break                                      # the 3.5 min demo: no new lines, wrap up
                if self.left() > self.reserve() + P("todo.top_up_min_left_s"):
                    if self.safely(self.top_up, True):
                        continue
                    # nothing new to put on the list (every item used today): a quiet spell, not a
                    # busy loop (review 25 Oct: a 9 h run spun at 100% CPU after about 2 h)
                    self.ctx.pacer.wait("gap", lambda: self.left() < self.reserve() + 45 or self.break_due())
                    continue
                break
            self.safely(self.maybe_glance)
            self.run_task(task)
            self.safely(self.after_task, task)
            if self.left() > self.reserve() + 60:
                self.ctx.pacer.wait("gap" if self.minutes >= 30 else "switch",
                                    lambda: self.left() < self.reserve() + 45 or self.break_due())

    def _link_waiting(self, item) -> bool:
        """A linked office note waits until its hybrid is finished (done or failed), or until a started
        hybrid will not be picked up again, so it can write about what was really found."""
        link = item.spec.get("_link")
        if link is None: return False
        if link.status in ("done", "failed", "deleted"): return False
        if link.status == "started" and not link.resume: return False
        return True

    def safely(self, step, *args):
        """Run one step between tasks; a desktop surprise (wrong window, no Save As box) is logged and
        the day goes on instead of the whole bot stopping (review 25 Oct)."""
        try:
            return step(*args)
        except Cut:
            raise
        except Exception as exc:
            self.log({"event": "step_error", "step": getattr(step, "__name__", "?"), "error": repr(exc)[:160]})
            return None

    def pick(self):
        """Next task: a cut task picked up again, the next line on the list, or now and then another one."""
        room0 = self.left() - self.reserve()
        ready = [t for t in self.paused if t.item.resume and t.item.status == "started"
                 and room0 > 45 + 50 + t.next_need_s]          # the step it stopped before must fit
        if ready and self.rng.random() < 0.6:
            task = ready[0]
            self.paused.remove(task)
            return task
        open_items = [i for i in self.todo.visible() if i.status == "open" and not i.personal
                      and i.spec.get("task") in TASKS        # follow ups (call samsung...) stay on the list
                      and not self._link_waiting(i)]
        open_items += [i for i in self.todo.visible() if i.status == "started" and i.resume and i.task is None
                       and self.now() - i.spec.get("_fx_started_at", -1e9) > P("task.look_again_after_s")]
        room = self.left() - self.reserve()
        fits = lambda i: P("task.min_seconds").get(i.spec["task"], 60) < room
        if self.minutes < P("plan.short_run_minutes") and open_items and open_items[0] is self.todo.visible()[0]:
            open_items = open_items[:1]                         # the 3.5 min demo: line one always runs
        else:
            open_items = [i for i in open_items if fits(i)]
        ready = [t for t in ready if room > 45 + 50 + t.next_need_s]   # the step it stopped before must fit
        if not open_items:
            if ready:
                self.paused.remove(ready[0]); return ready[0]
            return None
        item = open_items[0] if self.rng.random() >= P("todo.out_of_order_p") else self.rng.choice(open_items)
        cls = TASKS[item.spec["task"]]
        task = cls(self, item)
        item.task = task
        return task

    def run_task(self, task) -> None:
        item = task.item
        resumed = task.gen is not None
        if resumed:
            self.log({"event": "task_resume", "item": item.label})
            task.resume_prelude()
        else:
            task.gen = task.steps()
            task.started_at = self.now()
            self.log({"event": "task_start", "item": item.label, "kind": task.kind})
        cut_at = None
        if self.minutes >= 10 and self.rng.random() < P("task.interrupt_p"):
            cut_at = self.rng.randint(1, 3)
        checkpoints = 0
        try:
          try:
            for _ in task.gen:
                checkpoints += 1
                if self.stopped(): raise Cut("stop")
                if self.left() < self.reserve() + 50 + task.next_need_s: raise Cut("end of day")
                if cut_at == checkpoints: raise Cut("interrupted")
                if self.break_due() and task.resumable: raise Cut("break")
          except Cut:
            raise
          except Exception as exc:                          # wrong window, no Save As box, a bug
            self.log({"event": "task_error", "item": item.label, "error": repr(exc)[:160]})
            task.status = "failed"
            app = getattr(task.window, "app", "") or "app"
            task.note = ", " + self.rng.choice([f"{app} acting up, try later", f"could not finish in {app}, later"])
        except Cut as cut:
            self.desk.unsplit()                                # the next window used goes full screen again
            self.cut_task(task, cut.why)
            # a step that no longer fits is not the end of the day if shorter work still fits
            if cut.why == "stop" or (cut.why == "end of day" and self.left() < self.reserve() + 60): raise
            return
        self.desk.unsplit()                                    # side by side only while the task needs it
        item.status = task.status
        note = task.note if task.note.startswith(", ") or not task.note else ", " + task.note
        if task.status == "done":
            strike = self.cfg["todo"].get("strike", "note") == "dialog"
            says_done = note.lstrip(", ").startswith(("done", "finished", "ok", "filled", "sgd added"))
            if not strike and not says_done:                   # "done" first, unless the note already says it
                note = ", " + self.rng.choice(DONE_NOTES) + note
        if not note and task.status != "done":
            item.task = None                                   # nothing new to write on the list
        else:
            note = note if note else (", " + self.rng.choice(DONE_NOTES))
            item.pending_note = self._fit(item.label + item.note, note)
        item.task = None
        self.log({"event": "task_end", "item": item.label, "status": task.status, "note": note,
                  "seconds": round(self.now() - task.started_at, 1)})

    def _fit(self, label: str, note: str) -> str:
        """Keep a list line short enough that it never wraps in Writer (the bot moves line by line).
        The first part of the note says what happened ("page error", "done but some pages error"), so
        that part is kept and the extras at the end go first ("try again later", the file name)."""
        limit = P("todo.max_line_chars") - len(", started, tbc")
        parts = [p for p in note.split(", ") if p]
        while len(parts) > 1 and len(label) + 2 + len(", ".join(parts)) > limit:
            parts = parts[:-1]
        if parts and len(label) + 2 + len(parts[0]) > limit:   # still too long: the short form
            words = parts[0].split()
            while len(words) > 1 and len(label) + 2 + len(" ".join(words)) > limit:
                words = words[1:] if words[0] in ("coinmarketcap", "coingecko", "coinbase") else words[:-1]
            parts = [" ".join(words)]
        return ", " + ", ".join(parts) if parts else ""

    def cut_task(self, task, why: str) -> None:
        item = task.item
        self.safely(task.pause_here)
        item.status = "started"
        if task.resumable:
            item.resume = self.rng.random() < P("todo.resume_p")
            if item.resume: self.paused.append(task)
            else: item.task = None
        else:
            task.gen.close()
            item.task = None
            item.resume = self.rng.random() < P("todo.resume_p")   # a fresh browse of the same site later
        self.log({"event": "task_cut", "item": item.label, "why": why, "will_resume": item.resume})
        if why == "interrupted" and self.rng.random() < 0.5 and self.next_break is not None:
            self.next_break = min(self.next_break, self.now())     # the interruption was a break

    # list visits
    def maybe_glance(self) -> None:
        if self.rng.random() < P("todo.glance_p"):
            self.visit_list("glance")

    def after_task(self, task) -> None:
        win = task.window
        if (task.status in ("done", "failed") and win is not None and win in self.desk.mru and win.app in ("writer", "calc")
                and win is not self.todo.window and not win.extra.get("topic")
                and len(self.desk.find(win.app)) > 1 and self.rng.random() < P("doc.close_done_p")):
            if win.dirty and win.file: self.desk.save(win)
            self.desk.close(win)                             # done with this document
        followup = getattr(task, "followup", None)
        if (followup and task.status == "done" and followup not in {i.label for i in self.todo.items}
                and self.left() > self.reserve() + 60):
            self.pending_followups.append(followup)        # the open end of a note goes on the list
        if self.pending_followups or self.rng.random() < P("todo.strike_now_p") or self.left() < self.reserve() + 120:
            self.visit_list("cross off")

    def visit_list(self, why: str) -> None:
        todo = self.todo
        todo.open_list(why)
        self.mark_app("writer")
        self.ctx.pacer.wait("read")
        changed = todo.apply_pending(strike_ok=True)
        for item in todo.visible():
            if item.delete_at and self.now() >= item.delete_at and item.status == "open" and item.task is None:
                todo.delete_item(item); changed += 1
        if self.pending_followups:
            new = [Item(label, {"task": "followup", "kind": "followup"}) for label in self.pending_followups]
            self.pending_followups = []
            todo.add_items(new, self.wait); changed += 1
            self.log({"event": "followup_added", "items": [i.label for i in new]})
        if self.top_up(): changed += 1
        if (changed or todo.window.dirty) and self.rng.random() < P("todo.save_after_edit_p"):
            self.desk.save(todo.window)                  # not every time: the final update always saves

    def top_up(self, force: bool = False) -> bool:
        open_n = sum(1 for i in self.todo.visible() if i.status == "open" and not i.personal and i.spec.get("task") in TASKS)
        if not force and (open_n >= P("todo.add_when_open_below") or self.left() < 12 * 60): return False
        n = self.rng.randint(*P("todo.add_count"))
        new = self.draw_items(n, {i.label for i in self.todo.items})
        if not new: return False
        if self.desk.front is not self.todo.window: self.todo.open_list("add items"); self.mark_app("writer")
        self.todo.add_items(new, self.wait)
        if force: self.desk.save(self.todo.window)
        return True

    # breaks
    def break_due(self) -> bool:
        return self.next_break is not None and self.now() >= self.next_break and self.left() > self.reserve() + 90

    def maybe_break(self) -> None:
        if self.lunch_at is not None and self.now() >= self.lunch_at:
            self.lunch_at = None
            self.take_break("lunch")
            self.top_up(force=True)
            return
        if not self.break_due(): return
        kind = "onscreen" if getattr(self, "short_run_breaks", False) or self.rng.random() < P("break.onscreen_share") else "away"
        self.take_break(kind)
        self.next_break = None if getattr(self, "short_run_breaks", False) else self.now() + self._sitting()

    def take_break(self, kind: str) -> None:
        start = self.now()
        for w in list(self.desk.mru):                        # save before a break (agreed 23 Oct)
            if w.dirty and w.file: self.desk.save(w)
        personal = [i for i in self.todo.visible() if i.personal and i.status == "open"]
        if kind == "lunch":
            seconds = self.rng.uniform(*P("break.lunch_s"))
            seconds = min(seconds, max(60.0, self.left() - self.reserve() - 120))
            self.mark_app("away"); self.ctx.pacer.sleep_for("break_lunch", seconds)
            for i in personal:
                if i.spec.get("break") == "away": i.status, i.pending_note = "done", ", " + self.rng.choice(DONE_NOTES)
        elif kind == "away":
            seconds = self.rng.uniform(*P("break.short_s"))
            seconds = min(seconds, max(30.0, self.left() - self.reserve() - 60))
            self.mark_app("away"); self.ctx.pacer.sleep_for("break_away", seconds)
            for i in personal:
                if i.spec.get("break") == "away" and seconds >= i.spec.get("min_s", 60):
                    i.status, i.pending_note = "done", ", " + self.rng.choice(DONE_NOTES); break
        else:
            seconds = self.rng.uniform(*P("break.onscreen_s"))
            if self.minutes < 60: seconds = min(seconds, max(40.0, 0.1 * self.minutes * 60))
            seconds = min(seconds, max(30.0, self.left() - self.reserve() - 90))
            mine = [i for i in personal if i.spec.get("break") == "onscreen"]
            site = mine[0].spec["site"] if mine else self.rng.choice(self.cfg["break_sites"])
            win = self.desk.browser("break")
            self.mark_app("browser")
            own_tab = win.tabs < P("tabs.max_open")
            if own_tab:
                self.ctx.backend.hotkey("ctrl", "t"); win.tabs += 1; self.ctx.pacer.wait("settle")
            self.desk._skill("go_to_url", {"url": site})
            until = self.now() + seconds
            while self.now() < until and not self.stopped():
                self.desk._skill("scroll_and_read", {"bursts_range": [1, 3]})
                if self.rng.random() < 0.3: self.ctx.pacer.wait("read")
            # Leave the browser as the work left it: the break's page stayed in front and a task that
            # came back to "its" page searched Amazon instead (VM run 3, 25 Oct, finding 15).
            self.ctx.pacer.wait("step")
            if own_tab:
                self.ctx.backend.hotkey("ctrl", "w"); win.tabs -= 1
            else:
                self.ctx.backend.hotkey("alt", "left")
            self.ctx.pacer.wait("settle")
            if mine: mine[0].status, mine[0].pending_note = "done", ", " + self.rng.choice(DONE_NOTES)
        self.breaks.append({"kind": kind, "seconds": round(self.now() - start, 1)})
        self.log({"event": "break", "kind": kind, "seconds": round(self.now() - start, 1)})

    # end of the day
    def finish(self) -> None:
        if self.ctx.pacer.stopped():
            self.log({"event": "stopped"}); return
        todo = self.todo
        for t in self.paused:
            t.item.task = None

        def update_list():
            todo.open_list("final update")
            self.mark_app("writer")
            self.ctx.pacer.wait("read")
            todo.apply_pending(strike_ok=True)
            todo.final_update(self.minutes, self.rng, self.wait)
            self.desk.save(todo.window)
        self.safely(update_list)
        for win in list(self.desk.mru):                      # save everything, close every app:
            if win.app in ("writer", "calc") and win.dirty and win.file:
                self.safely(self.desk.save, win)            # one window failing never skips the rest
        for win in [w for w in list(self.desk.mru) if w.app != "harness"]:
            if win in self.desk.mru: self.safely(self.desk.close, win)
        self.log({"event": "workday_end", "overrun_s": round(self.now() - self.end, 1)})

    def summary(self) -> dict:
        total = sum(self.app_time.values()) or 1.0
        return {
            "minutes": self.minutes, "wpm": self.ctx.typer.wpm,
            "overrun_s": round(self.now() - self.end, 1),
            "todo_text": self.todo.doc.text if self.todo.doc else "",
            "items": [(i.label, i.status, i.note) for i in self.todo.items],
            "app_share": {k: round(v / total, 3) for k, v in sorted(self.app_time.items())},
            "breaks": self.breaks, "switches": self.desk.switches,
            "files": list(self.desk.saved_files),
        }
