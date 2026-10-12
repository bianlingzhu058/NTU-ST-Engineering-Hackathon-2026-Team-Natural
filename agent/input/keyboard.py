"""Typed text through injected desktop input and pacing components."""
import random
from ..interfaces import InputBackend
from ..timing import HumanPacer

QWERTY_NEIGHBOURS = {
    "q": "wa", "w": "qes", "e": "wrd", "r": "etf", "t": "ryg", "y": "tuh", "u": "yij", "i": "uok", "o": "ipl", "p": "o",
    "a": "qsz", "s": "awdx", "d": "sefc", "f": "drgv", "g": "fthb", "h": "gyjn", "j": "hukm", "k": "jil", "l": "ko",
    "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb", "b": "vghn", "n": "bhjm", "m": "njk",
}


class HumanTyper:
    """Types text with variable gaps and occasional corrected typing errors."""
    def __init__(self, backend: InputBackend, pacer: HumanPacer, rng: random.Random, typo_rate: float = .02):
        self._backend, self._pacer, self._rng, self._typo_rate = backend, pacer, rng, typo_rate

    def _wrong_key(self, char: str) -> str:
        pool = QWERTY_NEIGHBOURS.get(char.lower(), "")
        wrong = self._rng.choice(pool) if pool else "x"
        return wrong.upper() if char.isupper() else wrong

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
        for char in text:
            if not exact and char.isalpha() and self._rng.random() < self._typo_rate:
                self._backend.write(self._wrong_key(char))
                self._pacer.wait(key_pause)
                if self._rng.random() < 0.5:  # sometimes notice only after the next key
                    self._backend.write(char); self._pacer.wait(key_pause)
                    self._backend.press("backspace"); self._pacer.wait(key_pause)
                self._backend.press("backspace")
                self._pacer.wait(key_pause)
            self._backend.write(char)
            if not exact and char in ".!?\n": self._pacer.wait("think")
            elif char in " ,;:": self._pacer.wait("step" if (not exact and self._rng.random() < 0.15) else key_pause)
            else: self._pacer.wait(key_pause)
