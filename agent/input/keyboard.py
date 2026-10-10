"""Typed text through injected desktop input and pacing components."""
import random
from ..interfaces import InputBackend
from ..timing import HumanPacer


class HumanTyper:
    """Types text with variable gaps and optional corrected typing errors."""
    def __init__(self, backend: InputBackend, pacer: HumanPacer, rng: random.Random, typo_rate: float = .02, control=None):
        self._backend, self._pacer, self._rng, self._typo_rate, self._control = backend, pacer, rng, typo_rate, control

    def _act(self, method: str, *args) -> None:
        if self._control is not None: self._control.checkpoint()
        getattr(self._backend, method)(*args)
        if self._control is not None: self._control.checkpoint()
    def type_text(self, text: str) -> None:
        """Enter text and correct simulated single-character typos."""
        for char in text:
            if char.isalpha() and self._rng.random() < self._typo_rate:
                self._act("write", "x")
                self._pacer.wait("micro")
                self._act("press", "backspace")
            self._act("write", char)
            self._pacer.wait("micro" if char not in ".!? " else "step")
