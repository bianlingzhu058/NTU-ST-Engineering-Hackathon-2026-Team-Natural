"""The bot's own copy of a Writer document, and the messy way a person writes into it.

WriterDoc keeps a mirror of the text and the cursor, and every key it sends also updates the
mirror, so the bot always knows what is on the page and where the cursor is, without reading the
screen. Going back to a spot uses an anchor key (Ctrl+Home / Ctrl+End, or Home / End on a short
line) and then arrow keys, held down like a person does for longer runs.

Composer plans the final text first, then a messy route to it (report, "Our editing idea"):
  * slips fixed with Backspace (the typing model),
  * a forgotten word, inserted later by going back,
  * an extra word, deleted right away or after going back,
  * "blocking": a sentence typed too early is selected, cut with Ctrl+X and parked on its own line
    at the bottom, then pasted back where it belongs (or an unneeded one gets deleted),
  * a rewrite attempt: Enter at the start of the last sentence pushes it to its own line, a second
    version is typed, one of the two is kept and the other deleted,
  * "cleaning": stray spaces left by a cut get fixed.
At the end the mirror is compared with the plan; any difference is cleaned up by going back to it.
"""
from dataclasses import dataclass, field
import difflib
from ..behaviour.dist import clamp, ln_median
from ..behaviour.params import P
from ..input.keyboard import final_text

FILLERS = ["really", "also", "just", "maybe", "then", "quickly", "still", "some"]


class WriterDoc:
    """Mirror of one Writer document. ``short_lines`` means no paragraph wraps (the to do list),
    so Up/Down plus Home/End are safe anchors."""
    def __init__(self, context, short_lines: bool = False, name: str = ""):
        self.ctx, self.typer = context, context.typer
        self.text, self.cur, self.clip = "", 0, ""
        self.sel: tuple[int, int] | None = None
        self.short_lines, self.name = short_lines, name
        self.markers: dict[str, int] = {}
        self.counts = {"typed": 0, "deleted": 0, "jumps": 0, "cuts": 0, "pastes": 0}

    # mirror bookkeeping
    def _insert(self, s: str) -> None:
        at = self.cur
        self.text = self.text[:at] + s + self.text[at:]
        for k, m in self.markers.items():
            if m > at or (m == at and k.endswith("+")): self.markers[k] = m + len(s)
        self.cur = at + len(s)
        self.counts["typed"] += len(s)

    def _delete(self, a: int, b: int) -> None:
        if b <= a: return
        self.text = self.text[:a] + self.text[b:]
        for k, m in self.markers.items():
            if m >= b: self.markers[k] = m - (b - a)
            elif m > a: self.markers[k] = a
        self.cur = a if self.cur >= a else self.cur
        self.counts["deleted"] += b - a

    def lines(self) -> list[str]:
        return self.text.split("\n")

    def line_start(self, n: int) -> int:
        return sum(len(l) + 1 for l in self.lines()[:n])

    def line_of(self, i: int) -> tuple[int, int]:
        before = self.text[:i]
        return before.count("\n"), i - (before.rfind("\n") + 1)

    # keys that also update the mirror
    def type(self, s: str, mode: str = "compose", ctx: str = "prose") -> None:
        if not s: return
        self.sel = None
        ops = self.typer.type_text(s, ctx=ctx, mode=mode, keep_slips=False)
        shown = final_text(ops)
        self._insert(shown)

    def enter(self) -> None:
        self.sel = None
        self.typer.press("enter")
        self._insert("\n")

    def backspace(self, n: int = 1) -> None:
        n = min(n, self.cur)
        if n <= 0: return
        self.typer.hold_arrow("backspace", n)
        self._delete(self.cur - n, self.cur)

    def delete(self, n: int = 1) -> None:
        n = min(n, len(self.text) - self.cur)
        if n <= 0: return
        self.typer.hold_arrow("delete", n)
        self._delete(self.cur, self.cur + n)

    def _arrows(self, delta: int) -> None:
        if delta: self.typer.hold_arrow("right" if delta > 0 else "left", abs(delta))
        self.cur += delta

    def go(self, i: int) -> None:
        """Move the cursor to index i by the cheapest human route: arrows from here, or an anchor
        (Ctrl+Home, Ctrl+End, or on short lines Up/Down then Home/End) and then arrows."""
        i = max(0, min(len(self.text), i))
        if self.sel is not None and i == self.cur:
            # Text is still selected on screen (after a copy): one arrow there and back drops it, so
            # the next key does not replace it (review 25 Oct: ", tbc" vanished on the last line).
            first, back = ("left", "right") if self.cur > 0 else ("right", "left")
            if self.cur > 0 or self.text:
                self.typer.press(first); self.typer.press(back)
            self.sel = None
            return
        self.sel = None
        if i == self.cur: return
        self.counts["jumps"] += 1
        routes = {"here": abs(i - self.cur), "top": 2 + i, "bottom": 2 + len(self.text) - i}
        if self.short_lines:
            line, col = self.line_of(i)
            here_line, _ = self.line_of(self.cur)
            width = len(self.lines()[line])
            routes["line"] = abs(line - here_line) + 1 + min(col, width - col)
        best = min(routes, key=routes.get)
        if best == "top":
            self.typer.combo("ctrl", "home"); self.cur = 0
        elif best == "bottom":
            self.typer.combo("ctrl", "end"); self.cur = len(self.text)
        elif best == "line":
            line, col = self.line_of(i)
            here_line, _ = self.line_of(self.cur)
            if line != here_line: self.typer.hold_arrow("down" if line > here_line else "up", abs(line - here_line))
            width = len(self.lines()[line])
            if col <= width - col:
                self.typer.press("home"); self.cur = self.line_start(line)
            else:
                self.typer.press("end"); self.cur = self.line_start(line) + width
        self._arrows(i - self.cur)

    def select(self, a: int, b: int) -> None:
        """Select [a, b): go to a, hold Shift, arrow to b."""
        self.go(a)
        backend = self.ctx.backend
        backend.key_event("shift", True)
        self.typer.hold_arrow("right", b - a)
        backend.key_event("shift", False)
        self.cur, self.sel = b, (a, b)

    def cut(self) -> str:
        a, b = self.sel
        self.typer.combo("ctrl", "x")
        self.clip = self.text[a:b]
        self.cur = b
        self._delete(a, b)
        self.cur, self.sel = a, None
        self.counts["cuts"] += 1
        return self.clip

    def copy(self) -> str:
        a, b = self.sel
        self.typer.combo("ctrl", "c")
        self.clip = self.text[a:b]
        return self.clip

    def delete_selection(self) -> None:
        a, b = self.sel
        self.typer.press("delete")
        self.cur = b
        self._delete(a, b)
        self.cur, self.sel = a, None

    def paste(self) -> None:
        self.typer.combo("ctrl", "v")
        self._insert(self.clip)
        self.counts["pastes"] += 1

    def anchor_end(self) -> None:
        """Ctrl+End: the cursor goes to the end of the document (used when coming back to a doc)."""
        self.typer.combo("ctrl", "end")
        self.cur, self.sel = len(self.text), None

    def clean_to(self, target: str) -> int:
        """Fix every difference between the page and ``target`` by going back to it ("cleaning").
        Returns the number of fixes. Works from the end so earlier indices stay valid."""
        ops = difflib.SequenceMatcher(None, self.text, target, autojunk=False).get_opcodes()
        fixes = 0
        for tag, a, b, c, d in reversed(ops):
            if tag == "equal": continue
            fixes += 1
            if b > a:
                self.go(b)
                self.backspace(b - a)
            if d > c:
                self.go(a)
                self.type(target[c:d], mode="transcribe")
        return fixes


@dataclass
class Unit:
    """One piece of planned text: a sentence (or to do line) and an optional second wording."""
    text: str
    alt: str = ""
    newline_after: int = 0      # 0: a space follows (next sentence), 1: new paragraph or line, 2: blank line
    can_park: bool = True
    last: bool = False          # nothing follows it (end of what is being written)


@dataclass
class ComposeReport:
    forgotten: int = 0
    extra: int = 0
    parked: int = 0
    parked_deleted: int = 0
    rewrites: int = 0
    cleaned: int = 0
    leftover_slips: int = 0
    events: list = field(default_factory=list)


class Composer:
    """Writes planned text into a WriterDoc the messy way a person composes."""
    def __init__(self, doc: WriterDoc, rng, wait, extras: list[str] | None = None):
        self.doc, self.rng, self.wait = doc, rng, wait
        self.extras = list(extras or [])
        self.report = ComposeReport()
        self._pending: list[tuple[int, str]] = []    # (words typed when due, marker name)
        self._words = 0
        self._n = 0
        self._parked = False          # a sentence is parked: finish that before forgetting new words
        self._busy = False            # a park or rewrite is in progress: no going back for a forgotten word

    def _pause(self, name: str) -> None:
        median, sigma, low, high = P(name)
        self.wait(clamp(ln_median(self.rng, median, sigma), low, high))

    def _leftover_slip(self, word: str) -> str:
        """Plan a slip that stays on the page (7% of slips; Crump and Logan 2012)."""
        rate = P("typing.error_rate_prose") * P("typing.uncorrected_share")
        if len(word) < 4 or not word.isalpha() or self.rng.random() >= rate * len(word): return word
        # A wrong neighbour key, same length. Dropped or doubled letters ("untill", "tomorow") are in
        # Writer's AutoCorrect list, which would fix them on the page and put the bot's copy out of step.
        from ..input.keyboard import QWERTY_NEIGHBOURS
        i = self.rng.randrange(1, len(word) - 1)
        pool = QWERTY_NEIGHBOURS.get(word[i].lower(), "")
        if not pool: return word
        self.report.leftover_slips += 1
        return word[:i] + self.rng.choice(pool) + word[i + 1:]

    def write(self, units: list[Unit], at_end_marker: str = "write+") -> str:
        """Type all units at the cursor; returns the final text the page should now show."""
        doc = self.doc
        doc.markers[at_end_marker] = doc.cur
        self.end = at_end_marker
        start = doc.cur
        before, after = doc.text[:start], doc.text[start:]
        planned: list[str] = []
        units = [Unit(" ".join(self._leftover_slip(w) for w in u.text.split(" ")), u.alt, u.newline_after, u.can_park)
                 for u in units]
        units[-1].last = units[-1].last or units[-1].newline_after == 0
        park_at = self._choose_park(units)
        rewrite_at = self._choose_rewrite(units)
        parked_marker = None
        for index, unit in enumerate(units):
            if park_at and index == park_at[0]:
                parked_marker = self._jot_and_park(units[park_at[1]] if park_at[1] is not None else None)
            if parked_marker and park_at[1] == index:
                self._unpark(parked_marker, unit)
                parked_marker = None
            elif index == rewrite_at:
                self._rewrite(unit)
            else:
                self._sentence(unit.text)
            self._sep(unit)
            planned.append(unit.text + self._sep_text(unit))
        self._flush_pending(force=True)
        if parked_marker:     # an unneeded parked sentence: delete its line
            self._delete_parked(parked_marker)
        target = before + "".join(planned) + after
        fixes = doc.clean_to(target)
        self.report.cleaned += fixes
        doc.go(doc.markers.pop(at_end_marker, len(doc.text)))
        for k in [k for k in doc.markers if k[:1] in "fxp"]: doc.markers.pop(k)
        return target

    # pieces
    @staticmethod
    def _sep_text(unit: Unit) -> str:
        if unit.last: return ""
        return "\n" * unit.newline_after if unit.newline_after else " "

    def _sep(self, unit: Unit) -> None:
        if unit.last: return
        if unit.newline_after:
            for _ in range(unit.newline_after): self._go_end(); self.doc.enter()
            self.wait(clamp(ln_median(self.rng, *P("typing.paragraph_pause_s")[:2]), *P("typing.paragraph_pause_s")[2:]))
        else:
            self._type(" ")

    def _go_end(self) -> None:
        self.doc.go(self.doc.markers[self.end])

    def _type(self, s: str) -> None:
        self._go_end()
        self.doc.type(s)

    def _sentence(self, text: str, simple: bool = False) -> None:
        """Type one sentence in word bursts, maybe leaving out a word or adding an extra one.
        simple=True (a sentence that may get cut or rewritten): no word left for later."""
        words = text.split(" ")
        skip = extra_at = None
        if not simple and not self._parked and len(words) >= 4 and self.rng.random() < P("edit.forget_word_p"):
            options = [j for j in range(1, len(words) - 1) if len(words[j]) >= 3]
            if options: skip = self.rng.choice(options)
        if len(words) >= 3 and self.rng.random() < P("edit.extra_word_p"):
            extra_at = self.rng.randrange(1, len(words))
            if extra_at == skip: extra_at = None
        mean, sd, low, high = P("typing.pburst_words")
        burst, in_burst = max(low, min(high, round(self.rng.gauss(mean, sd)))), 0
        late_extra = None
        for j, word in enumerate(words):
            if j == extra_at:
                filler = self.rng.choice([w for w in FILLERS if w != word] + [words[j - 1]])
                self._type(filler + " ")
                self.report.extra += 1
                if simple or self.rng.random() < 0.6:
                    self.wait(self.rng.uniform(0.3, 1.2))
                    self.doc.backspace(len(filler) + 1)     # noticed straight away
                else:
                    self._n += 1
                    late_extra = (f"x{self._n}", len(filler) + 1)
                    self.doc.markers[late_extra[0]] = self.doc.cur - late_extra[1]
            if j == skip:
                self._n += 1
                name = f"f{self._n}"
                self.doc.markers[name] = self.doc.markers[self.end]
                self._pending.append((self._words + self.rng.randint(*P("edit.fix_delay_words")), name + ":" + word))
                self.report.forgotten += 1
                continue
            self._type(word if j == len(words) - 1 else word + " ")
            self._words += 1
            in_burst += 1
            if late_extra and self.rng.random() < 0.5:
                self._delete_late_extra(late_extra); late_extra = None
            if in_burst >= burst and j < len(words) - 1:
                self._pause("typing.pburst_pause_s")
                burst, in_burst = max(low, min(high, round(self.rng.gauss(mean, sd)))), 0
            self._flush_pending()
        if late_extra: self._delete_late_extra(late_extra)

    def _delete_late_extra(self, extra) -> None:
        name, length = extra
        self._pause("edit.reread_s")
        a = self.doc.markers.pop(name)
        self.doc.select(a, a + length)
        self.doc.delete_selection()
        self.report.events.append("deleted an extra word")

    def _flush_pending(self, force: bool = False) -> None:
        if self._busy and not force: return                  # not in the middle of a park or rewrite
        for due, item in list(self._pending):
            if not force and self._words < due: continue
            self._pending.remove((due, item))
            name, word = item.split(":", 1)
            self._pause("edit.reread_s")
            self.doc.go(self.doc.markers.pop(name))
            self.doc.type(word + " ")
            self.report.events.append(f"went back to add '{word}'")

    def _choose_park(self, units):
        """(index to jot at, index of the unit that belongs later) or (index, None) for an unneeded one."""
        # A sentence or a list line can be blocked, but not one right after a title (blank line).
        candidates = [i for i in range(1, len(units)) if units[i].can_park and units[i - 1].newline_after <= 1]
        if not candidates or self.rng.random() >= P("edit.park_p"): return None
        later = self.rng.choice(candidates)
        if self.rng.random() < P("edit.park_keep_p") and later >= 2:
            return (self.rng.randrange(1, later), later)
        if self.extras:
            return (self.rng.randrange(1, len(units)), None)
        return None

    def _choose_rewrite(self, units):
        options = [i for i, u in enumerate(units) if u.alt]
        if not options or self.rng.random() >= P("edit.rewrite_p"): return None
        return self.rng.choice(options)

    def _jot_and_park(self, unit: Unit | None) -> str:
        """Type a sentence too early, then block it (select), cut and park it on a new last line."""
        doc = self.doc
        self._flush_pending(force=True)                      # add back a forgotten word first
        self._parked = self._busy = True
        text = unit.text if unit else self.rng.choice(self.extras)
        start = doc.markers[self.end]
        self._sentence(text, simple=True)
        self._pause("edit.reread_s")
        # Sometimes the block grabs the space in front too, so the text it leaves runs together
        # and gets cleaned up right after ("cleaning the mess").
        messy = start > 0 and doc.text[start - 1] == " " and self.rng.random() < P("edit.clean_leftover_p")
        doc.select(start - 1 if messy else start, doc.markers[self.end])
        doc.cut()
        keep = doc.markers[self.end]                         # where writing goes on after the park
        doc.anchor_end()
        doc.enter()
        doc.paste()                                          # parked on its own line at the bottom
        doc.markers[self.end] = keep                         # (inserting at the end moved it along)
        self._n += 1
        name = f"p{self._n}"
        doc.markers[name] = len(doc.text) - len(doc.clip)
        doc.markers[name + "_end+"] = len(doc.text)
        self.report.parked += 1
        self.report.events.append("blocked a sentence, cut it and parked it on its own line")
        if messy:
            doc.go(start - 1)
            doc.type(" ", mode="transcribe")                 # cleaning: put back the space the cut took
            self.report.cleaned += 1
            a = doc.markers[name]
            if doc.text[a:a + 1] == " ":                     # and the stray space at the start of the parked line
                doc.go(a + 1); doc.backspace(1)
        return name

    def _unpark(self, name: str, unit: Unit) -> None:
        """Cut the parked line back up into its place and clean up the empty line it leaves."""
        doc = self.doc
        a, b = doc.markers.pop(name), doc.markers.pop(name + "_end+")
        self._pause("edit.reread_s")
        doc.select(a, b)
        doc.cut()
        doc.backspace(1)                                     # the now empty line
        self._go_end()
        doc.paste()
        self.report.events.append("moved the parked sentence back")
        self._parked = self._busy = False

    def _delete_parked(self, name: str) -> None:
        doc = self.doc
        a, b = doc.markers.pop(name), doc.markers.pop(name + "_end+")
        self._pause("edit.reread_s")
        doc.select(a - 1, b)                                 # the line and the line break before it
        doc.delete_selection()
        self.report.parked_deleted += 1
        self._parked = self._busy = False
        self.report.events.append("deleted the parked sentence, not needed")

    def _rewrite(self, unit: Unit) -> None:
        """Push the sentence to its own line, try the other wording, keep one."""
        doc = self.doc
        self._flush_pending(force=True)                      # add back a forgotten word first
        was_busy, self._busy = self._busy, True
        keep_new = self.rng.random() < P("edit.rewrite_keep_new_p")
        first, second = (unit.alt, unit.text) if keep_new else (unit.text, unit.alt)
        start = doc.markers[self.end]
        self._sentence(first, simple=True)
        self._pause("edit.reread_s")
        doc.go(start)
        doc.enter()                                          # the sentence drops to its own line
        doc.go(start)                                        # back to the end of the line above
        doc.markers[self.end] = start
        self._sentence(second, simple=True)
        self._pause("edit.reread_s")
        mid = doc.markers[self.end]                          # end of the second version
        if keep_new:                                         # keep the new one: delete the line below
            doc.select(mid, mid + 1 + len(first))
            doc.delete_selection()
        else:                                                # the old one was better
            doc.select(start, mid)
            doc.delete_selection()
            doc.delete(1)                                    # join the old sentence back up
        doc.markers[self.end] = start + len(unit.text)
        self._busy = was_busy
        self.report.rewrites += 1
        self.report.events.append("rewrote a sentence" if keep_new else "tried a rewrite, kept the old one")
