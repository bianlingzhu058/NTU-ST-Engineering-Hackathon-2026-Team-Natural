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

    def type_text(self, text: str) -> None:
        """Enter text with per-key pauses, word and sentence pauses, and corrected typos."""
        for char in text:
            if char.isalpha() and self._rng.random() < self._typo_rate:
                self._backend.write(self._wrong_key(char))
                self._pacer.wait("micro")
                if self._rng.random() < 0.5:  # sometimes notice only after the next key
                    self._backend.write(char); self._pacer.wait("micro")
                    self._backend.press("backspace"); self._pacer.wait("micro")
                self._backend.press("backspace")
                self._pacer.wait("micro")
            self._backend.write(char)
            if char in ".!?\n": self._pacer.wait("think")
            elif char in " ,;:": self._pacer.wait("step" if self._rng.random() < 0.15 else "micro")
            else: self._pacer.wait("micro")
