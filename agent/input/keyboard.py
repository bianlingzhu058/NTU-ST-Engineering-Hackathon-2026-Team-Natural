"""Typed text through injected desktop input and pacing components."""
import random
from ..interfaces import InputBackend
from ..timing import HumanPacer


class HumanTyper:
    """Types text with variable gaps and optional corrected typing errors."""
    def __init__(self, backend: InputBackend, pacer: HumanPacer, rng: random.Random, typo_rate: float = .02):
        self._backend, self._pacer, self._rng, self._typo_rate = backend, pacer, rng, typo_rate
    def type_text(self, text: str) -> None:
        """Enter text and correct simulated single-character typos."""
        for char in text:
            if char.isalpha() and self._rng.random() < self._typo_rate:
                self._backend.write("x")
                self._pacer.wait("micro")
                self._backend.press("backspace")
            self._backend.write(char)
            self._pacer.wait("micro" if char not in ".!? " else "step")
