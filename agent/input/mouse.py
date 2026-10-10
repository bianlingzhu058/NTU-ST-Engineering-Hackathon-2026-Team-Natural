"""Curved pointer movement built from primitive backend operations."""
import random
from ..interfaces import InputBackend
from ..timing import HumanPacer


class HumanMouse:
    """Moves through sampled intermediate points and clicks a target."""
    def __init__(self, backend: InputBackend, pacer: HumanPacer, rng: random.Random, steps: int = 14, control=None):
        self._backend, self._pacer, self._rng, self._steps, self._control = backend, pacer, rng, max(2, steps), control
    def move(self, x: float, y: float) -> None:
        """Move along a gently curved path to a target coordinate."""
        for i in range(1, self._steps + 1):
            t = i / self._steps
            bend = self._rng.uniform(-12, 12) * 4 * t * (1 - t)
            if self._control is not None: self._control.checkpoint()
            self._backend.move_to(x * t + bend, y * t - bend)
            self._pacer.wait("micro")
    def click(self, x: float, y: float, radius: int = 4) -> None:
        """Move to a small random offset and click."""
        self.move(x + self._rng.randint(-radius, radius), y + self._rng.randint(-radius, radius))
        if self._control is not None: self._control.checkpoint()
        self._backend.click()
