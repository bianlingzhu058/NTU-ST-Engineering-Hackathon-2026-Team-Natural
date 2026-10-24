"""The bot's own to do list in Writer, and a small Calc sheet model.

The list is short lines (no wrapping), so going to an item is Up/Down then Home/End, like a person
moving through a short list. Layout on the page:

    todo 24 oct            <- title
                           <- empty line
    check bitcoin on coingecko, done, saved in crypto prices 24 oct
    write meeting notes, started, tbc
    call dentist
    ...
                           <- empty line (only once the progress line is added at the end)
    2 of 4 done, rest tbc
"""
from dataclasses import dataclass, field
from ..behaviour.params import P
from .doc import Composer, Unit, WriterDoc


@dataclass
class Item:
    label: str
    spec: dict
    personal: bool = False
    status: str = "open"          # open, done, failed, started, deleted
    note: str = ""                # what is written after the label on the page
    struck: bool = False
    pending_note: str = ""        # decided but not yet written on the page
    delete_at: float | None = None
    task: object = None
    resume: bool = False
    files: list = field(default_factory=list)


class TodoList:
    def __init__(self, context, desk, config: dict, log):
        self.ctx, self.desk, self.cfg, self.log = context, desk, config, log
        self.items: list[Item] = []
        self.window = None
        self.doc: WriterDoc | None = None
        self.title = ""
        self.copied_tbc = False

    # layout
    def visible(self) -> list[Item]:
        return [i for i in self.items if i.status != "deleted"]

    def line_no(self, item: Item) -> int:
        return 2 + self.visible().index(item)

    def line_end(self, item: Item) -> int:
        n = self.line_no(item)
        return self.doc.line_start(n) + len(self.doc.lines()[n])

    def item_text(self, item: Item) -> str:
        return item.label + item.note

    def expected_text(self, extra: str = "") -> str:
        return self.title + "\n\n" + "\n".join(self.item_text(i) for i in self.visible()) + extra

    # writing
    def write_new(self, title: str, items: list[Item], wait) -> None:
        """Open Writer, compose the title and the lines the messy way, save in the To do folder."""
        self.window = self.desk.open_app("writer", "to do list")
        self.doc = WriterDoc(self.ctx, short_lines=True, name="todo")
        self.window.doc = self.doc
        self.title, self.items = title, list(items)
        units = [Unit(title, newline_after=2, can_park=False)]
        units += [Unit(i.label, newline_after=1 if k < len(items) - 1 else 0) for k, i in enumerate(items)]
        units[-1].newline_after = 0
        composer = Composer(self.doc, self.ctx.rng, wait, extras=[])
        target = composer.write(units)
        self._resync(target)
        self.log({"event": "todo_written", "title": self.title, "items": [i.label for i in self.items],
                  "edits": composer.report.events})
        return composer.report

    def _resync(self, target: str) -> None:
        """Take the labels as they ended up on the page (a slip may have stayed in)."""
        lines = target.split("\n")
        self.title = lines[0]
        for item, line in zip(self.items, lines[2:]):
            item.label = line

    def open_list(self, why: str) -> None:
        self.desk.focus(self.window, why)

    def add_items(self, new: list[Item], wait) -> None:
        """New lines at the end of the list (when it runs low, or after lunch)."""
        self.open_list("add items")
        last = self.visible()[-1]
        self.doc.go(self.line_end(last))
        self.ctx.pacer.wait("think")
        units = [Unit(i.label, newline_after=0) for i in new]
        self.doc.enter()
        first_line = self.line_no(last) + 1
        for k, u in enumerate(units):
            if k: self.doc.enter()
            Composer(self.doc, self.ctx.rng, wait).write([u])
            new[k].label = self.doc.lines()[first_line + k]     # as it ended up on the page
        self.items.extend(new)
        self.window.dirty = True
        self.log({"event": "todo_added", "items": [i.label for i in new]})

    def apply_pending(self, strike_ok: bool) -> int:
        """Write every decided note (done / failed / started) that is not on the page yet."""
        changed = 0
        for item in self.visible():
            if not item.pending_note: continue
            if item.status == "done" and not item.struck and strike_ok:
                item.struck = self.strike(item)
            self.doc.go(self.line_end(item))
            self.ctx.pacer.wait("think")
            self.doc.type(item.pending_note)
            item.note += item.pending_note
            item.pending_note = ""
            changed += 1
            self.log({"event": "todo_note", "item": item.label, "note": item.note, "struck": item.struck})
        if changed: self.window.dirty = True
        return changed

    def strike(self, item: Item) -> bool:
        """Cross the item text out. Only with the keyboard route set in config (VM check pending)."""
        if self.cfg["todo"].get("strike", "note") != "dialog": return False
        start = self.doc.line_start(self.line_no(item))
        self.doc.select(start, start + len(item.label))
        ctx = self.ctx
        for key in self.cfg["todo"]["strike_keys"]:
            if key == "WAIT":
                ctx.pacer.wait("settle")
                if ctx.verify_window(self.cfg["todo"]["strike_dialog_title"], tries=4) is False:
                    ctx.backend.press("escape")
                    self.log({"event": "strike_failed", "item": item.label})
                    return False
                continue
            if "+" in key: ctx.backend.hotkey(*key.split("+"))
            else: ctx.backend.press(key)
            ctx.pacer.wait("step")
        self.doc.sel = None
        return True

    def delete_item(self, item: Item) -> None:
        """A reminder that turned out unnecessary: select the line with its line break, Delete."""
        n = self.line_no(item)
        start = self.doc.line_start(n)
        end = start + len(self.doc.lines()[n])
        if item is self.visible()[-1]: self.doc.select(start - 1, end)
        else: self.doc.select(start, end + 1)
        self.ctx.pacer.wait("think")
        self.doc.delete_selection()
        item.status = "deleted"
        self.window.dirty = True
        self.log({"event": "todo_deleted", "item": item.label})

    def final_update(self, minutes: float, rng, wait) -> None:
        """Open items get ', tbc' (typed once, copied, pasted on the rest); started ones ', started, tbc';
        a progress line on runs over 5 min."""
        doc = self.doc
        open_items = [i for i in self.visible() if i.status in ("open", "started") and not i.pending_note]
        first = None
        for item in open_items:
            suffix = ", started, tbc" if item.status == "started" else ", tbc"
            doc.go(self.line_end(item))
            if item.status == "open" and first is not None:
                doc.paste()                                   # the ', tbc' copied from the first one
            else:
                self.ctx.pacer.wait("think")
                doc.type(suffix)
                if item.status == "open" and first is None:
                    first = item
                    end = doc.cur
                    doc.select(end - len(suffix), end)        # select ', tbc' and copy it
                    doc.copy()
                    doc.go(end)
            item.note += suffix
            self.ctx.pacer.wait("step")
        if minutes > P("todo.progress_line_min_minutes"):
            from .content import PROGRESS
            work = [i for i in self.visible() if not i.personal]
            done = sum(1 for i in work if i.status == "done")
            line = rng.choice(PROGRESS).format(done=done, total=len(work))
            doc.go(len(doc.text))
            doc.enter(); doc.enter()
            Composer(doc, rng, wait).write([Unit(line)])
            self.progress = doc.lines()[-1]                  # as it ended up (a slip may have stayed)
        self.window.dirty = True
        self.log({"event": "todo_final", "text": doc.text})


class CalcSheet:
    """Mirror of a small Calc table: header, rows, a Total row. The cursor is tracked by cell."""
    def __init__(self, context, headers: list[str], sum_cols: list[int]):
        self.ctx, self.headers, self.sum_cols = context, headers, sum_cols
        self.rows: list[list[str]] = []
        self.has_total = False
        self.row = 0                     # 0-based row the cursor is on, column A after Enter

    def _type_row(self, values: list[str]) -> None:
        ctx = self.ctx
        ctx.pacer.wait("burst" if self.row else "think")
        for c, value in enumerate(values):
            numeric = value.replace(".", "").replace(",", "").isdigit()
            ctx.typer.type_text(value, ctx="number" if numeric else "cell", mode="transcribe")
            if c < len(values) - 1: ctx.backend.press("tab")
            ctx.pacer.wait("cell")
        ctx.backend.press("enter")
        self.row += 1

    def start(self) -> None:
        self.ctx.backend.hotkey("ctrl", "home"); self.row = 0
        self._type_row(self.headers)

    def go_next_free_row(self) -> None:
        """Coming back to the sheet: Ctrl+Home, Ctrl+Down to the last filled row, then down one
        (or onto the Total row, which the new rows replace)."""
        ctx = self.ctx
        ctx.backend.hotkey("ctrl", "home"); ctx.pacer.wait("step")
        ctx.backend.hotkey("ctrl", "down"); ctx.pacer.wait("step")
        last = len(self.rows) + (1 if self.has_total else 0)
        self.row = last
        if not self.has_total:
            ctx.backend.press("down"); self.row += 1
        else:
            self.has_total = False       # the next rows go over the old Total row

    def add_row(self, values: list[str]) -> None:
        self._type_row(values)
        self.rows.append(values)

    def total(self, label: str = "Total") -> None:
        ctx = self.ctx
        ctx.pacer.wait("think")
        ctx.typer.type_text(label, ctx="cell")
        last = len(self.rows) + 1
        for c in range(1, len(self.headers)):
            ctx.backend.press("tab")
            if c in self.sum_cols:
                ctx.pacer.wait("think")
                col = chr(ord("A") + c)
                ctx.typer.type_text(f"=SUM({col}2:{col}{last})", ctx="cell")
            ctx.pacer.wait("cell")
        ctx.backend.press("enter")
        self.has_total = True
        self.row += 1
