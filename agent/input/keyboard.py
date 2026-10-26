"""Typed text through injected desktop input and pacing components."""
import random
from ..interfaces import InputBackend
from ..timing import HumanPacer

QWERTY_NEIGHBOURS = {
    "q": "wa", "w": "qes", "e": "wrd", "r": "etf", "t": "ryg", "y": "tuh", "u": "yij", "i": "uok", "o": "ipl", "p": "o",
    "a": "qsz", "s": "awdx", "d": "sefc", "f": "drgv", "g": "fthb", "h": "gyjn", "j": "hukm", "k": "jil", "l": "ko",
    "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb", "b": "vghn", "n": "bhjm", "m": "njk",
}

# QWERTY left-hand keys, for same-hand / hand-alternation and left-hand inter-key timing.
LEFT_HAND = set("qwertasdfgzxcvb12345`")

# Deliberate "look-and-key" pauses (numbers, filenames, URLs) carry an occasional hesitation
# while the hand reads the next character. A RUN of the same key (e.g. the zeros in 1000000)
# is not read one digit at a time -- it is one fast burst off a single key -- so a repeat inside
# these contexts skips the hesitation and uses the tail-free "repeat" pause instead. Prose
# (the "micro" pause) is already fast and tail-free, so it is left exactly as it is.
DELIBERATE_PAUSES = {"keydata", "field", "cell", "url"}


class HumanTyper:
    """Types text with variable gaps and occasional corrected typing errors."""
    def __init__(self, backend: InputBackend, pacer: HumanPacer, rng: random.Random, typo_rate: float = .02):
        self._backend, self._pacer, self._rng, self._typo_rate = backend, pacer, rng, typo_rate

    def _wrong_key(self, char: str) -> str:
        pool = QWERTY_NEIGHBOURS.get(char.lower(), "")
        wrong = self._rng.choice(pool) if pool else "x"
        return wrong.upper() if char.isupper() else wrong

    def _gap_factor(self, prev: str, nxt: str) -> float:
        """Multiplier on the flight time from ``prev`` to ``nxt`` so inter-key timing depends on
        the digraph the way a real hand does: a repeated key is fastest (the second 'p' in
        'apple'), the first key after a space is slower, same-hand pairs are a touch slower than
        alternating ones, the left hand a touch slower, and the number row is slow (Dhakal 2018)."""
        if not nxt:
            return 1.0
        if prev in ("", " ", "\n", "\t"):
            return 1.35                                    # word initiation: first key of a word
        if prev == nxt:
            return 0.78                                    # repeated key: fastest ("pp" in apple)
        if nxt.isdigit() and not prev.isdigit():
            return 2.1                                     # reaching up to the number row
        same_hand = (prev.lower() in LEFT_HAND) == (nxt.lower() in LEFT_HAND)
        factor = 1.05 if same_hand else 0.95               # same hand slower, alternation faster
        if nxt.lower() in LEFT_HAND:
            factor *= 1.03                                 # left hand a touch slower
        return factor

    def _tap(self, key: str) -> None:
        """Press a key, hold it a human moment, then release it, so each keystroke has a
        varied dwell time (key-down to key-up) instead of a uniform near-zero hold."""
        k = {"\n": "enter", "\t": "tab"}.get(key, key)
        self._backend.key_down(k)
        self._pacer.wait("hold")
        self._backend.key_up(k)

    def type_text(self, text: str, exact: bool = False, key_pause: str = "micro") -> None:
        """Enter text with per-key pauses, word and sentence pauses, and corrected typos.

        exact=True types the string verbatim: no typo injection and no sentence pause on
        ".". Use it for URLs, addresses and filenames, where the final text MUST be correct
        (a typo'd URL 404s or triggers a search) and "." is a normal key, not a sentence
        end. Address-bar autocomplete also makes backspace-correction unreliable, so for
        those strings we never introduce an error to correct. (Research: uncorrected error
        rate is zero on URLs; "." -> letter is a ~206 ms keypress, not a sentence pause.)

        key_pause names the inter-key pause kind: "micro" (~0.09s) for ordinary prose typing,
        a slower kind like "keydata" for deliberate numeric/spreadsheet entry so the keys are
        visibly keyed rather than appearing to pop in all at once.
        """
        n = len(text)
        prev = ""
        for i, char in enumerate(text):
            nxt = text[i + 1] if i + 1 < n else ""
            # Reaching for Shift before a capital takes a beat longer than a plain key —
            # a small context-dependent pause, not a fixed one.
            if not exact and char.isupper() and not prev.isupper():
                self._pacer.wait("step" if self._rng.random() < 0.3 else key_pause)
            placed = False
            if not exact and char.isalpha() and self._rng.random() < self._typo_rate:
                # Humans make several kinds of slip, not just one. Pick a type at random:
                # substitution (a neighbouring key), transposition (this key and the next in the
                # wrong order), omission (ran ahead and skipped this key) or insertion (an extra
                # neighbouring key slipped in). Each is noticed and backspaced out, so the final
                # text is always correct.
                can_swap = nxt.isalpha()
                kind = self._rng.choice(("substitute", "transpose", "omit", "insert")) if can_swap else "substitute"
                if kind == "substitute":
                    self._tap(self._wrong_key(char)); self._pacer.wait(key_pause)
                    if self._rng.random() < 0.5:  # sometimes notice only after the next key
                        self._tap(char); self._pacer.wait(key_pause)
                        self._tap("backspace"); self._pacer.wait(key_pause)
                    self._tap("backspace"); self._pacer.wait(key_pause)
                elif kind == "transpose":  # typed this key and the next in the wrong order
                    self._tap(nxt); self._pacer.wait(key_pause)
                    self._tap(char); self._pacer.wait(key_pause)
                    self._tap("backspace"); self._pacer.wait(key_pause)
                    self._tap("backspace"); self._pacer.wait(key_pause)
                elif kind == "omit":  # ran ahead to the next key, caught the skip, backed up
                    self._tap(nxt); self._pacer.wait(key_pause)
                    self._tap("backspace"); self._pacer.wait(key_pause)
                else:  # insert: typed the right key, then an extra neighbouring key slipped in
                    self._tap(char); self._pacer.wait(key_pause)
                    self._tap(self._wrong_key(char)); self._pacer.wait(key_pause)
                    self._tap("backspace"); self._pacer.wait(key_pause)
                    placed = True   # the correct char is already down; do not retype it below
            if not placed:
                self._tap(char)
            # Inter-key flight time, shaped by the digraph (repeats fast, word-starts slower, ...).
            factor = self._gap_factor(char, nxt)
            repeat_burst = nxt == char and char.strip() != "" and key_pause in DELIBERATE_PAUSES
            if not exact and char in ".!?\n": self._pacer.wait("think")
            elif repeat_burst: self._pacer.wait("repeat", scale=factor)   # same key again: one fast burst, no look-and-key hesitation
            elif char in " ,;:": self._pacer.wait("step" if (not exact and self._rng.random() < 0.15) else key_pause, scale=factor)
            else: self._pacer.wait(key_pause, scale=factor)
            prev = char
