"""Human typing: research-timed keystrokes with realistic slips, corrections, key holds and rollover.

How a string is typed, in two passes (ported from our v1.2 branch):

1. Plan. Walk the target text as a typist would. Sometimes make a slip (wrong letter, missing
   letter or extra letter in the measured 53/26/21 split), keep typing for the measured detection
   lag (0 to 4+ keys), then Backspace back to the last correct character and carry on. In prose a
   small share of slips is left in; in exact contexts (URLs, file names, cells) the final text
   always equals the target.
2. Time and play. Each keystroke gets a gap from a lognormal around this person's typing speed,
   scaled by the cited factors (word start, repeated letter, hand, digits, delimiters), plus
   sentence pauses in prose. Every key is a real key down and a real key up with a measured hold
   time (about 116 ms); about a quarter of keys overlap the next one (rollover).

Every number comes from agent/behaviour/params.py with its source.
"""
import collections
import random
from ..behaviour.dist import clamp, ln_mean, ln_median, weighted
from ..behaviour.params import P
from ..interfaces import InputBackend

QWERTY_NEIGHBOURS = {
    "q": "wa", "w": "qes", "e": "wrd", "r": "etf", "t": "ryg", "y": "tuh", "u": "yij", "i": "uok", "o": "ipl", "p": "o",
    "a": "qsz", "s": "awdx", "d": "sefc", "f": "drgv", "g": "fthb", "h": "gyjn", "j": "hukm", "k": "jil", "l": "ko",
    "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb", "b": "vghn", "n": "bhjm", "m": "njk",
}
LEFT = set("qwertasdfgzxcvb12345`~!@#$%")
SHIFTED = set('~!@#$%^&*()_+{}|:"<>?') | set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
DELIMITERS = set("./@-:_\\")
EXACT_CONTEXTS = {"url", "filename", "cell", "query", "number", "noslip"}
_KEY_PAUSE_CTX = {"url": "url", "field": "filename", "keydata": "cell"}


class HumanTyper:
    """Types text with research-timed keystrokes through separate key down and key up events.

    ``typo_rate`` (optional) overrides the prose slip rate; tests use 0 and 1."""
    def __init__(self, backend: InputBackend, pacer, rng: random.Random, typo_rate: float | None = None,
                 wpm: float | None = None):
        self._backend, self._pacer, self._rng = backend, pacer, rng
        self._typo_rate = typo_rate
        self.wpm = round(wpm if wpm is not None else rng.uniform(*P("typing.wpm_range")), 1)
        self.base_iki_ms = P("typing.iki_per_wpm") / self.wpm
        self.last_plan: list[tuple] = []
        # holds_ms keeps the last 20000 key holds only, so a 9 h run does not grow memory without end
        self.stats = {"keys": 0, "slips": 0, "backspaces": 0, "holds_ms": collections.deque(maxlen=20000)}

    # planning
    def _neighbour(self, char: str) -> str:
        if char.isdigit():
            return str(min(9, max(0, int(char) + self._rng.choice((-1, 1)))))
        pool = QWERTY_NEIGHBOURS.get(char.lower(), "")
        wrong = self._rng.choice(pool) if pool else char
        return wrong.upper() if char.isupper() else wrong

    def _rate(self, ctx: str) -> float:
        if ctx == "noslip": return 0.0   # e.g. Explorer type-ahead, where Backspace means "go up a folder"
        if ctx in EXACT_CONTEXTS:
            return 0.0 if self._typo_rate == 0 else P("typing.error_rate_exact")
        return P("typing.error_rate_prose") if self._typo_rate is None else self._typo_rate

    def plan(self, text: str, ctx: str = "prose", keep_slips: bool = True) -> list[tuple]:
        """Keystroke ops ("char", c, tag) / ("back", first) / ("fixed",) ending with ``text`` on
        screen (except deliberately uncorrected prose slips)."""
        rng, rate = self._rng, self._rate(ctx)
        lags = P("typing.detect_lag_weights")
        target, typed, i, lag, ops = text, "", 0, None, []
        safe_until = -1            # right after a fix the person types the next key carefully
        while True:
            if lag is not None and (lag <= 0 or i >= len(target)):
                first = True
                while not target.startswith(typed):
                    typed = typed[:-1]
                    ops.append(("back", first)); first = False
                i, lag = len(typed), None
                safe_until = i
                ops.append(("fixed",))
                continue
            if i >= len(target):
                break
            char = target[i]
            slippable = char.isalpha() or (ctx == "number" and char.isdigit())
            if lag is None and slippable and i > safe_until and rng.random() < rate:
                kind = weighted(rng, P("typing.error_types"))
                if kind == "substitution":
                    typed += self._neighbour(char); ops.append(("char", typed[-1], "error"))
                elif kind == "insertion":
                    typed += self._neighbour(char); ops.append(("char", typed[-1], "error"))
                    typed += char; ops.append(("char", char, ""))
                # omission: the key is simply not pressed
                i += 1
                if ctx not in EXACT_CONTEXTS and keep_slips and self._typo_rate is None and rng.random() < P("typing.uncorrected_share"):
                    target = typed + target[i:]   # the slip stays on screen, as 7% of slips do
                    i = len(typed)
                else:
                    lag = rng.choices(range(len(lags)), weights=lags, k=1)[0]
                    if lag == len(lags) - 1: lag += rng.randint(*P("typing.detect_lag_tail_extra"))
                continue
            typed += char; ops.append(("char", char, "")); i += 1
            if lag is not None: lag -= 1
        self.last_plan = ops
        return ops

    # timing
    def _iki(self, prev: str | None, cur: str, ctx: str, mode: str) -> float:
        rng, base = self._rng, self.base_iki_ms
        if prev in (None, " ", "\n"): factor = P("typing.word_initial_factor")
        elif prev == cur: factor = P("typing.repeat_factor")
        else:
            same = (prev.lower() in LEFT) == (cur.lower() in LEFT)
            factor = P("typing.same_hand_factor") if same else P("typing.alternate_hand_factor")
            if cur.lower() in LEFT: factor *= P("typing.left_hand_factor")
        mean = base * factor
        if mode == "compose" and cur.isalpha() and prev not in (None, " "): mean += P("typing.within_word_compose_ms")
        ms = max(P("typing.iki_floor_ms"), ln_mean(rng, mean, P("typing.iki_sigma")))
        if cur.isdigit() and prev is not None and not prev.isdigit(): ms *= P("typing.letter_to_digit_factor")
        if ctx != "prose" and prev is not None and prev in DELIMITERS: ms *= P("typing.chunk_boundary_factor")
        if cur in SHIFTED and (prev is None or prev not in SHIFTED):
            ms += ln_mean(rng, P("typing.shift_lead_ms"), P("typing.shift_lead_sigma"))
        if mode == "compose" and cur == " ": ms += P("typing.word_extra_compose_ms")
        if ctx == "prose" and prev in (".", "!", "?") and cur in (" ", "\n"):
            ms += ln_mean(rng, base * 2 + (P("typing.sentence_extra_compose_ms") if mode == "compose" else 0),
                          P("typing.sentence_pause_sigma"))
            if mode == "compose" and rng.random() < P("typing.sentence_long_pause_p"):
                median, sigma, low, high = P("typing.sentence_long_pause_s")
                ms += clamp(ln_median(rng, median, sigma), low, high) * 1000
        return ms

    def hold_ms(self) -> float:
        low, high = P("typing.hold_clamp_ms")
        ms = clamp(ln_mean(self._rng, P("typing.hold_mean_ms"), P("typing.hold_sigma")), low, high)
        self.stats["holds_ms"].append(ms)
        return ms

    def schedule(self, ops: list[tuple], ctx: str, mode: str) -> list[tuple[float, str, str, bool]]:
        """Turn ops into timed (t_ms, kind, key, down) events, including holds and rollover."""
        rng, events, t, prev = self._rng, [], 0.0, None
        last_up_index, after_fix = None, False
        for op in ops:
            if op[0] == "fixed":
                after_fix = True
                continue
            if op[0] == "back":
                gap = ln_mean(rng, P("typing.first_backspace_ms"), 0.4) if op[1] else \
                    max(P("typing.iki_floor_ms"), ln_mean(rng, self.base_iki_ms * P("typing.later_backspace_factor"), 0.3))
                kind, key = "key", "backspace"
            else:
                key, kind = op[1], "char"
                if after_fix:
                    gap = ln_mean(rng, P("typing.after_fix_ms") * (0.62 if key.lower() in LEFT else 1.03), 0.3)
                else:
                    gap = self._iki(prev, key, ctx, mode)
                    if op[2] == "error": gap *= P("typing.error_key_factor")
                after_fix = False
                prev = key
            t += gap
            hold = self.hold_ms()
            if last_up_index is not None and kind == "char" and rng.random() < P("typing.rollover_p"):
                # Rollover: this key goes down a moment BEFORE the previous one comes up (about 30 ms
                # overlap, Dhakal 2018). The next key comes early; the previous key's hold stays as
                # drawn (about 116 ms). Stretching the hold instead made holds about 150 ms (VM 25 Oct).
                previous_up = events[last_up_index][0]
                previous_down = events[last_up_index - 1][0]
                overlap = min(100.0, ln_mean(rng, P("typing.rollover_overlap_ms"), 0.5))
                if events[last_up_index][1] == "char" and previous_up - overlap > previous_down + P("typing.iki_floor_ms"):
                    t = min(t, previous_up - overlap)
            events.append((t, kind, key, True))
            events.append((t + hold, kind, key, False))
            last_up_index = len(events) - 1
        events.sort(key=lambda e: (e[0], not e[3]))
        return events

    # playback
    def play(self, events: list[tuple[float, str, str, bool]]) -> None:
        now = 0.0
        for t, kind, key, down in events:
            if self._pacer.stopped(): return
            self._pacer.tiny((t - now) / 1000.0)
            now = t
            if down:
                self.stats["keys"] += 1
                if key == "backspace": self.stats["backspaces"] += 1
            if kind == "key": self._backend.key_event(key, down)
            elif key == "\n": self._backend.key_event("enter", down)
            elif key == "\t": self._backend.key_event("tab", down)
            else: self._backend.char_event(key, down)

    def type_text(self, text: str, exact: bool = False, key_pause: str = "micro", ctx: str | None = None,
                  mode: str = "transcribe", keep_slips: bool = True) -> list[tuple]:
        """Plan, time and type ``text``.

        ctx: prose, url, filename, cell, number, query. When not given it is derived from the old
        main arguments: exact=True with key_pause url / field / keydata means url / filename / cell.
        mode: "compose" when the person is writing their own words (slower between words,
        longer sentence pauses), "transcribe" when copying a known string.
        keep_slips=False: every slip gets fixed (the document editor plans its leftover slips itself).
        """
        if ctx is None:
            if exact:
                ctx = _KEY_PAUSE_CTX.get(key_pause, "url")
                if ctx == "cell" and text.replace(".", "").replace(",", "").isdigit(): ctx = "number"
            else:
                ctx = "prose"
        ops = self.plan(str(text), ctx, keep_slips)
        self.stats["slips"] += sum(1 for op in ops if op[0] == "char" and op[2] == "error") + \
            sum(1 for op in ops if op[0] == "back" and op[1])
        self.play(self.schedule(ops, ctx, mode))
        return ops

    def key_gap(self) -> float:
        """One ordinary gap in seconds between consecutive named keys."""
        return max(P("typing.iki_floor_ms"), ln_mean(self._rng, self.base_iki_ms * 1.6, P("typing.iki_sigma"))) / 1000.0

    # named keys and shortcuts with human holds
    def press(self, key: str, emit: bool = True) -> None:
        """One named key: key down, hold about 116 ms, key up."""
        if emit: self._backend.key_event(key, True)
        self._pacer.tiny(self.hold_ms() / 1000.0)
        if emit: self._backend.key_event(key, False)

    def press_sequence(self, *keys: str) -> None:
        for index, key in enumerate(keys):
            if index: self._pacer.tiny(self.key_gap())
            if "+" in key: self.combo(*key.split("+"))
            else: self.press(key)

    def hold_arrow(self, key: str, count: int) -> None:
        """Move the cursor ``count`` steps: single taps for a few, holding the key down (Windows
        auto-repeat: 0.5 s delay, about 30 per second) for longer runs, the way a person does."""
        if count <= 0: return
        if count <= 6:
            for i in range(count):
                if i: self._pacer.tiny(self.key_gap())
                self.press(key)
            return
        delay, every = P("typing.arrow_repeat_s")
        self._backend.key_event(key, True)
        self._pacer.tiny(delay)
        for _ in range(count - 2):
            self._backend.key_event(key, True)    # auto-repeat sends further key downs
            self._pacer.tiny(every)
        self._backend.key_event(key, True)
        self._pacer.tiny(self.hold_ms() / 1000.0)
        self._backend.key_event(key, False)

    def combo(self, *keys: str, emit: bool = True) -> None:
        """A shortcut such as Ctrl+S: modifier down, a short lead, the key with a hold, release in reverse."""
        *mods, key = keys
        for mod in mods:
            if emit: self._backend.key_event(mod, True)
            self._pacer.tiny(ln_mean(self._rng, P("typing.shift_lead_ms") * 0.6, P("typing.shift_lead_sigma")) / 1000.0)
        self.press(key, emit=emit)
        for mod in reversed(mods):
            self._pacer.tiny(self._rng.uniform(*P("typing.modifier_release_s")))
            if emit: self._backend.key_event(mod, False)


def final_text(ops: list[tuple]) -> str:
    """What a plan leaves on screen (used by tests and the editor's self check)."""
    out = ""
    for op in ops:
        if op[0] == "char": out += op[1]
        elif op[0] == "back": out = out[:-1]
    return out
