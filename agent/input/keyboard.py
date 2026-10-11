"""Human typing: research-timed keystrokes with realistic errors, corrections, holds and rollover.

How a string is typed, in two passes:

1. Plan. Walk the target text as a typist would. Occasionally make an error (substitution,
   omission or insertion in the measured 53/26/21 split), keep typing for the measured detection
   lag (0 to 4+ keys), then Backspace back to the last correct character and carry on. In prose a
   small share of errors is left uncorrected; in exact contexts (URLs, filenames, cells) the final
   text always equals the target.
2. Time and play. Each keystroke gets an inter-key interval from a lognormal around the persona's
   base IKI, scaled by the cited factors (word start, repetition, hand, digits, delimiters,
   familiarity), plus sentence pauses in prose only. Every key is a real down event and a real up
   event with a measured hold time; about a quarter of keys overlap the next one (rollover).

A "." inside a URL, email address or number is an ordinary key here: the previous version paused
up to 25 seconds after every dot, which no measurement supports (CMU: "." to a letter 206 ms).
"""
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
DELIMITERS = set("./@-:_")
EXACT_CONTEXTS = {"url", "filename", "cell", "query", "number"}


class HumanTyper:
    """Types text with research-timed keystrokes, through separate key down/up events."""
    def __init__(self, backend: InputBackend, pacer, rng: random.Random, persona):
        self._backend, self._pacer, self._rng, self._persona = backend, pacer, rng, persona
        self.last_plan: list[tuple] = []  # kept for tests and the dry-run printout

    # planning
    def _neighbour(self, char: str) -> str:
        if char.isdigit():  # adjacent digit on the number row (Wiseman 2011: wrong digit is the top slip)
            return str(min(9, max(0, int(char) + self._rng.choice((-1, 1)))))
        pool = QWERTY_NEIGHBOURS.get(char.lower(), "")
        wrong = self._rng.choice(pool) if pool else char
        return wrong.upper() if char.isupper() else wrong

    def plan(self, text: str, ctx: str = "prose") -> list[tuple]:
        """Keystroke ops ("char", c, tag) / ("back", first) that end with the screen showing the text.

        Returns the plan; the final typed string equals ``text`` except for deliberately
        uncorrected prose errors.
        """
        rng = self._rng
        rate = P("typing.error_rate_exact") if ctx in EXACT_CONTEXTS else P("typing.error_rate_prose")
        if ctx == "number": rate = P("sheet.digit_slip_p")
        lags = P("typing.detect_lag_weights")
        target, typed, i, lag, ops = text, "", 0, None, []
        while True:
            if lag is not None and (lag <= 0 or i >= len(target)):
                first = True
                while not target.startswith(typed):
                    typed = typed[:-1]
                    ops.append(("back", first)); first = False
                i, lag = len(typed), None
                ops.append(("fixed",))
                continue
            if i >= len(target):
                break
            char = target[i]
            slippable = char.isalpha() or (ctx == "number" and char.isdigit())
            if lag is None and slippable and rng.random() < rate:
                kind = weighted(rng, P("typing.error_types"))
                if kind == "substitution":
                    typed += self._neighbour(char); ops.append(("char", typed[-1], "error"))
                elif kind == "insertion":
                    typed += self._neighbour(char); ops.append(("char", typed[-1], "error"))
                    typed += char; ops.append(("char", char, ""))
                # omission: the key is simply not pressed
                i += 1
                if ctx not in EXACT_CONTEXTS and rng.random() < P("typing.uncorrected_share"):
                    target = typed + target[i:]  # the slip stays on screen, as 7% of slips do
                    i = len(typed)
                else:
                    lag = rng.choices(range(len(lags)), weights=lags, k=1)[0]
                    if lag == len(lags) - 1: lag += rng.randint(*P("typing.detect_lag_tail_extra"))  # "4 or more"
                continue
            typed += char; ops.append(("char", char, "")); i += 1
            if lag is not None: lag -= 1
        self.last_plan = ops
        return ops

    # timing
    def _iki(self, prev: str | None, cur: str, ctx: str, mode: str, familiar: bool) -> float:
        rng, base = self._rng, self._persona.base_iki_ms
        if ctx == "number" and cur.isdigit():
            median, sigma, low, high = P("sheet.digit_key_s")
            return clamp(ln_median(rng, median, sigma), low, high) * 1000.0
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
        if familiar: ms *= P("typing.familiar_factor")
        if ctx == "prose" and prev in (".", "!", "?") and cur in (" ", "\n"):
            ms += ln_mean(rng, base * 2 + (P("typing.sentence_extra_compose_ms") if mode == "compose" else 0),
                          P("typing.sentence_pause_sigma"))
            if mode == "compose" and rng.random() < P("typing.sentence_long_pause_p"):
                median, sigma, low, high = P("typing.sentence_long_pause_s")
                ms += clamp(ln_median(rng, median, sigma), low, high) * 1000
        return ms

    def _hold(self) -> float:
        low, high = P("typing.hold_clamp_ms")
        return clamp(ln_mean(self._rng, P("typing.hold_mean_ms"), P("typing.hold_sigma")), low, high)

    def schedule(self, ops: list[tuple], ctx: str, mode: str, familiar: bool) -> list[tuple[float, str, str, bool]]:
        """Turn ops into timed (t_ms, kind, key, down) events, including holds and rollover."""
        rng, events, t, prev = self._rng, [], 0.0, None
        last_up_index, after_fix = None, False
        for op in ops:
            if op[0] == "fixed":
                after_fix = True
                continue
            if op[0] == "back":
                gap = ln_mean(rng, P("typing.first_backspace_ms"), 0.4) if op[1] else \
                    max(P("typing.iki_floor_ms"), ln_mean(rng, self._persona.base_iki_ms * P("typing.later_backspace_factor"), 0.3))
                kind, key = "key", "backspace"
            else:
                key, kind = op[1], "char"
                if after_fix:
                    gap = ln_mean(rng, P("typing.after_fix_ms") * (0.62 if key.lower() in LEFT else 1.03), 0.3)
                else:
                    gap = self._iki(prev, key, ctx, mode, familiar)
                    if op[2] == "error": gap *= P("typing.error_key_factor")
                after_fix = False
                prev = key
            t += gap
            hold = self._hold()
            if last_up_index is not None and rng.random() < P("typing.rollover_p"):
                # rollover: the previous key is still down when this one goes down
                previous = events[last_up_index]
                overlap = min(100.0, ln_mean(rng, P("typing.rollover_overlap_ms"), 0.5))
                events[last_up_index] = (max(previous[0], t + overlap),) + previous[1:]
            events.append((t, kind, key, True))
            events.append((t + hold, kind, key, False))
            last_up_index = len(events) - 1
        events.sort(key=lambda e: (e[0], not e[3]))
        return events

    # playback
    def play(self, events: list[tuple[float, str, str, bool]]) -> None:
        now = 0.0
        for t, kind, key, down in events:
            self._pacer.tiny((t - now) / 1000.0)
            now = t
            if kind == "key": self._backend.key_event(key, down)
            elif key == "\n": self._backend.key_event("enter", down)
            elif key == "\t": self._backend.key_event("tab", down)
            else: self._backend.char_event(key, down)

    def type_text(self, text: str, ctx: str = "prose", mode: str = "transcribe", familiar: bool = False) -> list[tuple]:
        """Plan, time and type ``text``. ctx: prose, url, filename, cell, query, number."""
        ops = self.plan(text, ctx)
        self.play(self.schedule(ops, ctx, mode, familiar))
        return ops

    def type_exact(self, text: str, ctx: str = "url") -> None:
        """Type with research timing but no slips (Chrome's bypass phrase must arrive contiguous)."""
        ops = [("char", c, "") for c in text]
        self.last_plan = ops
        self.play(self.schedule(ops, ctx, "transcribe", False))

    def key_gap(self) -> float:
        """One ordinary inter-key interval in seconds (between consecutive named keys)."""
        return max(P("typing.iki_floor_ms"), ln_mean(self._rng, self._persona.base_iki_ms, P("typing.iki_sigma"))) / 1000.0

    def press_sequence(self, *keys: str) -> None:
        """Several named keys in a row (Enter Enter, Tab, Shift+Right...) with typing-model gaps."""
        for index, key in enumerate(keys):
            if index: self._pacer.tiny(self.key_gap())
            if "+" in key: self.combo(*key.split("+"))
            else: self.press(key)

    def press(self, key: str) -> None:
        """One named key with a human hold time."""
        self._backend.key_event(key, True)
        self._pacer.tiny(self._hold() / 1000.0)
        self._backend.key_event(key, False)

    def combo(self, *keys: str) -> None:
        """A shortcut such as Ctrl+L: modifier down, a Shift-like lead, the key, release in reverse."""
        *mods, key = keys
        for mod in mods:
            self._backend.key_event(mod, True)
            self._pacer.tiny(ln_mean(self._rng, P("typing.shift_lead_ms"), P("typing.shift_lead_sigma")) / 1000.0)
        self.press(key)
        for mod in reversed(mods):
            self._pacer.tiny(self._rng.uniform(*P("typing.modifier_release_s")))
            self._backend.key_event(mod, False)


def final_text(ops: list[tuple]) -> str:
    """What a plan leaves on screen (used by tests)."""
    out = ""
    for op in ops:
        if op[0] == "char": out += op[1]
        elif op[0] == "back": out = out[:-1]
    return out
