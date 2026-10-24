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
from datetime import datetime
import os
from pathlib import Path
import json
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
        facts_path = root / "config" / "page_facts.json"
        self.facts = json.loads(facts_path.read_text(encoding="utf-8")) if facts_path.exists() else {}
        self.log_rows: list[dict] = []
        self.desk = Desk(context, self.cfg, self.log)
        self.todo = TodoList(context, self.desk, self.cfg, self.log)
        self.fail_notes = FAIL_NOTES
        self.paused: list = []
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
        for w in self.desk.mru:
            if w.extra.get("topic") == topic and w.doc is not None: return w
        return None

    def saved_work_files(self) -> list[str]:
        """The bot's own older files in Documents that are not open now (safe to move)."""
        folder = os.path.join(self.desk.profile, self.cfg["files"]["work_folder"])
        open_files = {w.file for w in self.desk.mru}
        try:
            names = os.listdir(folder)
        except OSError:
            return []
        out = []
        for n in names:
            stem, ext = os.path.splitext(n)
            if ext in (".odt", ".ods") and stem not in open_files and stem not in self.moved_files:
                out.append(stem)
        return out

    # planning the list
    def _label(self, spec: dict) -> tuple[str, dict]:
        spec = dict(spec)
        label = self.rng.choice(spec["labels"])
        if "{coin}" in label:
            spec["_coin"] = self.rng.choice(COIN_LABELS)
            label = label.replace("{coin}", spec["_coin"])
        label = label.replace("{person}", self.rng.choice(PEOPLE)).replace("{team}", self.rng.choice(TEAMS))
        return label, spec

    def _usable(self, spec: dict) -> bool:
        return not spec.get("facts") or spec["facts"] in self.facts

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
        return out

    def plan(self) -> list[Item]:
        for limit, (lo, hi) in P("todo.items_by_minutes"):
            if self.minutes <= limit: break
        items = self.draw_items(self.rng.randint(lo, hi), set())
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
        self.desk.save(self.todo.window, folder=folder, name=self.fill(self.cfg["todo"]["file"]))
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
        self.desk.explorer(); self.mark_app("explorer")
        self.desk._skill("explorer_navigate", {"path": "%USERPROFILE%\\" + parent})
        ctx = self.ctx
        ctx.pacer.wait("think")
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
        since_task = 0
        while not self.stopped():
            if self.left() < self.reserve() + 40:
                break
            self.maybe_break()
            if self.left() < self.reserve() + 40:
                break
            task = self.pick()
            if task is None:
                if self.left() > self.reserve() + 150:
                    self.top_up(force=True)
                    continue
                break
            self.maybe_glance()
            self.run_task(task)
            since_task += 1
            self.after_task(task)
            if self.left() > self.reserve() + 60:
                self.ctx.pacer.wait("gap" if self.minutes >= 30 else "switch",
                                    lambda: self.left() < self.reserve() + 45 or self.break_due())

    def pick(self):
        """Next task: a cut task picked up again, the next line on the list, or now and then another one."""
        ready = [t for t in self.paused if t.item.resume and t.item.status == "started"]
        if ready and self.rng.random() < 0.6:
            task = ready[0]
            self.paused.remove(task)
            return task
        open_items = [i for i in self.todo.visible() if i.status == "open" and not i.personal]
        open_items += [i for i in self.todo.visible() if i.status == "started" and i.resume and i.task is None]
        room = self.left() - self.reserve()
        fits = lambda i: P("task.min_seconds").get(i.spec["task"], 60) < room
        open_items = [i for i in open_items if fits(i)]
        ready = [t for t in ready if room > 45]
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
            for _ in task.gen:
                checkpoints += 1
                if self.stopped(): raise Cut("stop")
                if self.left() < self.reserve() + 50: raise Cut("end of day")
                if cut_at == checkpoints: raise Cut("interrupted")
                if self.break_due() and task.resumable: raise Cut("break")
        except Cut as cut:
            self.cut_task(task, cut.why)
            if cut.why in ("stop", "end of day"): raise
            return
        item.status = task.status
        note = task.note if task.note.startswith(", ") or not task.note else ", " + task.note
        if task.status == "done":
            strike = self.cfg["todo"].get("strike", "note") == "dialog"
            note = (", " + self.rng.choice(DONE_NOTES) if not strike else "") + note
        note = note if note else (", " + self.rng.choice(DONE_NOTES))
        item.pending_note = self._fit(item.label, note)
        item.task = None
        self.log({"event": "task_end", "item": item.label, "status": task.status, "note": note,
                  "seconds": round(self.now() - task.started_at, 1)})

    def _fit(self, label: str, note: str) -> str:
        """Keep a list line short enough that it never wraps in Writer (the bot moves line by line):
        drop the front part of the note, then the middle, down to ', done'."""
        limit = P("todo.max_line_chars") - len(", started, tbc")
        parts = [p for p in note.split(", ") if p]
        while parts and len(label) + 2 + len(", ".join(parts)) > limit:
            parts = parts[1:] if len(parts) > 2 else parts[-1:] if len(parts) == 2 and len(parts[-1]) < len(parts[0]) else parts[:1]
            if len(parts) == 1 and len(label) + 2 + len(parts[0]) > limit:
                parts = ["done"]; break
        return ", " + ", ".join(parts) if parts else ""

    def cut_task(self, task, why: str) -> None:
        item = task.item
        task.pause_here()
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
        if self.rng.random() < P("todo.strike_now_p") or self.left() < self.reserve() + 120:
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
        if self.top_up(): changed += 1
        if changed or todo.window.dirty:
            self.desk.save(todo.window)

    def top_up(self, force: bool = False) -> bool:
        open_n = sum(1 for i in self.todo.visible() if i.status == "open" and not i.personal)
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
            if win.tabs < P("tabs.max_open"):
                self.ctx.backend.hotkey("ctrl", "t"); win.tabs += 1; self.ctx.pacer.wait("settle")
            self.desk._skill("go_to_url", {"url": site})
            until = self.now() + seconds
            while self.now() < until and not self.stopped():
                self.desk._skill("scroll_and_read", {"bursts_range": [1, 3]})
                if self.rng.random() < 0.3: self.ctx.pacer.wait("read")
            if mine: mine[0].status, mine[0].pending_note = "done", ", " + self.rng.choice(DONE_NOTES)
        self.breaks.append({"kind": kind, "seconds": round(self.now() - start, 1)})
        self.log({"event": "break", "kind": kind, "seconds": round(self.now() - start, 1)})

    # end of the day
    def finish(self) -> None:
        if self.ctx.pacer.stopped():
            self.log({"event": "stopped"}); return
        todo = self.todo
        todo.open_list("final update")
        self.mark_app("writer")
        self.ctx.pacer.wait("read")
        todo.apply_pending(strike_ok=True)
        for t in self.paused:
            t.item.task = None
        todo.final_update(self.minutes, self.rng, self.wait)
        self.desk.save(todo.window)
        for win in list(self.desk.mru):                      # save everything, close every app
            if win.app in ("writer", "calc") and win.dirty:
                if win.file: self.desk.save(win)
        for win in [w for w in list(self.desk.mru) if w.app != "harness"]:
            self.desk.close(win)
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
