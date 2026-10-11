"""Curved pointer movement built from primitive backend operations."""
import random
from ..interfaces import InputBackend
from ..timing import HumanPacer

CORNER_MARGIN = 40  # never let a path or target touch a screen corner


class HumanMouse:
    """Moves from the current position along a curved path, overshoots slightly, then clicks."""
    def __init__(self, backend: InputBackend, pacer: HumanPacer, rng: random.Random, steps: int = 14):
        self._backend, self._pacer, self._rng, self._steps = backend, pacer, rng, max(4, steps)

    def _clamp(self, x: float, y: float) -> tuple[float, float]:
        w, h = self._backend.screen_size()
        return min(max(x, CORNER_MARGIN), w - CORNER_MARGIN), min(max(y, CORNER_MARGIN), h - CORNER_MARGIN)

    def move(self, x: float, y: float) -> None:
        """Move along a quadratic Bezier from the current position with easing and a small overshoot."""
        x, y = self._clamp(x, y)
        x0, y0 = self._backend.position()
        dist = ((x - x0) ** 2 + (y - y0) ** 2) ** 0.5
        if dist < 2: return
        cx = (x0 + x) / 2 + self._rng.uniform(-0.25, 0.25) * dist
        cy = (y0 + y) / 2 + self._rng.uniform(-0.25, 0.25) * dist
        over = self._rng.uniform(0.02, 0.08) if dist > 150 else 0.0
        ex, ey = x + (x - x0) * over, y + (y - y0) * over  # overshoot target
        steps = max(4, int(self._steps * min(2.0, dist / 400 + 0.6)))
        for i in range(1, steps + 1):
            t = i / steps
            t = t * t * (3 - 2 * t)  # smoothstep easing
            px = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * ex
            py = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * ey
            self._backend.move_to(*self._clamp(px, py))
            self._pacer.wait("micro")
        if over:
            for i in (0.5, 1.0):  # correct back onto the target
                self._backend.move_to(*self._clamp(ex + (x - ex) * i, ey + (y - ey) * i))
                self._pacer.wait("micro")

    def click(self, x: float, y: float, radius: int = 4) -> None:
        """Move to a small random offset and click."""
        self.move(x + self._rng.randint(-radius, radius), y + self._rng.randint(-radius, radius))
        self._pacer.wait("micro")
        self._backend.click()

    def drift(self) -> None:
        """Small idle movement, as a reader resting a hand on the mouse, biased back toward the middle."""
        x0, y0 = self._backend.position()
        width, height = self._backend.screen_size()
        pull = 0.12  # without this the pointer parks on the clamp edge after a margin click
        self.move(x0 + (width / 2 - x0) * pull + self._rng.uniform(-120, 120),
                  y0 + (height / 2 - y0) * pull + self._rng.uniform(-80, 80))
