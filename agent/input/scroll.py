"""Bursty scrolling via the input backend and shared pacer."""
import random
from ..interfaces import InputBackend
from ..timing import HumanPacer


class HumanScroller:
    """Scrolls in bounded bursts with pauses and occasional reversals."""
    def __init__(self, backend: InputBackend, pacer: HumanPacer, rng: random.Random, burst_size: int = 4):
        self._backend, self._pacer, self._rng, self._burst_size = backend, pacer, rng, burst_size

    def scroll_bursts(self, bursts: int = 3) -> None:
        """Perform a chosen count of variable scroll bursts, each a few wheel notches with reading pauses."""
        for _ in range(bursts):
            direction = 1 if self._rng.random() < .10 else -1  # negative = down the page
            notches = self._rng.randint(1, max(1, self._burst_size))
            for _ in range(notches):
                self._backend.scroll(direction)
                self._pacer.wait("micro")
            self._pacer.wait("read")
