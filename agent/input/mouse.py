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
            self._pacer.wait("glide")  # FIX: fast per-step gap so the move is ~0.2s, not a 2s slow hover
        if over:
            for i in (0.5, 1.0):  # correct back onto the target
                self._backend.move_to(*self._clamp(ex + (x - ex) * i, ey + (y - ey) * i))
                self._pacer.wait("glide")

    def click(self, x: float, y: float, radius: int = 4) -> None:
        """Move to a small random offset and click with a human press duration.

        FIX (VM): a zero-gap LEFTDOWN+LEFTUP is sometimes ignored by apps / over
        VNC. Settle after the move so the cursor has arrived, then hold the button
        briefly before releasing. Falls back to a plain click on backends without
        separate down/up (e.g. the fake backend used in tests).
        """
        self.move(x + self._rng.randint(-radius, radius), y + self._rng.randint(-radius, radius))
        self._pacer.wait("settle")  # let the cursor arrive / window react before pressing
        down = getattr(self._backend, "mouse_down", None)
        up = getattr(self._backend, "mouse_up", None)
        if callable(down) and callable(up):
            down(); self._pacer.wait("micro"); up()  # human press-and-release gap
        else:
            self._backend.click()

    def drift(self) -> None:
        """Small idle movement, as a reader resting a hand on the mouse.

        FIX: smaller range (a subtle twitch, not a wide slow glide across the
        page) so it reads as a hand resting on the mouse, not an animation.
        """
        x0, y0 = self._backend.position()
        self.move(x0 + self._rng.uniform(-35, 35), y0 + self._rng.uniform(-25, 25))
