"""Human mouse movement and clicking, timed by Fitts's law and shaped like measured strokes.

One move is planned the way motor-control research describes it:

  time      MT = a + log2(D / W + 1) / TP, with this person's throughput TP (3.7 to 4.9 bits/s)
            and intercept a (0.10 to 0.23 s), Soukoreff and MacKenzie 2004.
  shape     one fast primary submovement that lands short (88 to 97% of the way) or, on long
            moves, overshoots (34% of moves over 200 px), then a slower corrective submovement
            (Meyer et al. 1988 model; proportions from the Balabit dataset).
  path      a gentle quadratic curve bowing to this person's side, straightness about 0.94 to
            0.99 (Balabit median 0.83 over all strokes).
  speed     a minimum-jerk profile warped so deceleration is longer than acceleration; symmetric
            profiles are the top feature bot detectors use (BeCAPTCHA-Mouse).
  events    60 to 100 move events per second, so the step count scales with movement time
            instead of being fixed (a fixed count is itself a bot signature).
  click     a short verification pause, then button down, a measured hold (median 95 ms), up.
"""
import math
import random
from ..behaviour.dist import clamp, ln_median
from ..behaviour.params import P
from ..interfaces import InputBackend

EDGE_MARGIN = 6  # keep off the exact screen edge (hot corners, taskbar auto-hide)


class HumanMouse:
    """Moves and clicks through the backend with research-shaped timing."""
    def __init__(self, backend: InputBackend, pacer, rng: random.Random, persona):
        self._backend, self._pacer, self._rng, self._persona = backend, pacer, rng, persona
        self.last_moves: list[dict] = []  # per-move plan summaries, for tests and evidence

    def _clamp(self, x: float, y: float) -> tuple[float, float]:
        w, h = self._backend.screen_size()
        return clamp(x, EDGE_MARGIN, w - 1 - EDGE_MARGIN), clamp(y, EDGE_MARGIN, h - 1 - EDGE_MARGIN)

    def movement_time(self, distance: float, width: float) -> float:
        W = max(4.0, width)
        mt = self._persona.intercept_s + math.log2(distance / W + 1) / self._persona.throughput
        return mt * self._rng.lognormvariate(0.0, P("mouse.mt_sigma"))

    @staticmethod
    def _skewed(tau: float, k: float) -> float:
        tau = tau ** k
        return tau ** 3 * (10 - 15 * tau + 6 * tau * tau)

    def _curve(self, x0, y0, x1, y1):
        d = math.hypot(x1 - x0, y1 - y0) or 1.0
        off = d * self._rng.uniform(*P("mouse.curve_offset")) * self._persona.curve_side
        cx, cy = (x0 + x1) / 2 - (y1 - y0) / d * off, (y0 + y1) / 2 + (x1 - x0) / d * off
        return lambda u: ((1 - u) ** 2 * x0 + 2 * (1 - u) * u * cx + u * u * x1,
                          (1 - u) ** 2 * y0 + 2 * (1 - u) * u * cy + u * u * y1)

    def _segment(self, x0, y0, x1, y1, seconds: float) -> int:
        path, k = self._curve(x0, y0, x1, y1), self._rng.uniform(*P("mouse.skew_k"))
        steps = max(3, int(seconds * self._persona.event_hz))
        for i in range(1, steps + 1):
            self._backend.move_to(*self._clamp(*path(self._skewed(i / steps, k))))
            self._pacer.tiny(seconds / steps * self._rng.uniform(*P("mouse.step_jitter")))
        return steps

    def move(self, x: float, y: float, width: float = 20.0, height: float = 20.0) -> None:
        """Move to a target of the given size centred at (x, y), with scatter and a correction."""
        rng = self._rng
        div = P("mouse.scatter_div")
        ex = x + clamp(rng.gauss(0, width / div), -width * .4, width * .4)
        ey = y + clamp(rng.gauss(0, height / div), -height * .4, height * .4)
        ex, ey = self._clamp(ex, ey)
        x0, y0 = self._backend.position()
        distance = math.hypot(ex - x0, ey - y0)
        if distance < 2: return
        total = self.movement_time(distance, min(width, height))
        p_over, over_min_d, over_lo, over_hi = P("mouse.overshoot")
        frac = rng.uniform(over_lo, over_hi) if distance > over_min_d and rng.random() < p_over \
            else rng.uniform(*P("mouse.primary_reach"))
        px, py = x0 + (ex - x0) * frac, y0 + (ey - y0) * frac
        t1 = total * rng.uniform(*P("mouse.primary_time_share"))
        steps = self._segment(x0, y0, px, py, t1)
        steps += self._segment(px, py, ex, ey, max(0.05, total - t1))
        self.last_moves.append({"distance": round(distance), "seconds": round(total, 3), "steps": steps,
                                "overshoot": frac > 1})

    def click(self, x: float, y: float, width: float = 20.0, height: float = 20.0) -> None:
        """Move onto a target, pause to verify, then press with a measured hold."""
        self.move(x, y, width, height)
        self.press_button()

    def press_button(self) -> None:
        rng = self._rng
        p_fast, fast_lo, fast_hi = P("mouse.preclick_fast")
        median, sigma, cap = P("mouse.preclick_slow")
        verify = rng.uniform(fast_lo, fast_hi) if rng.random() < p_fast else min(cap, ln_median(rng, median, sigma))
        self._pacer.tiny(verify)
        hold_median, hold_sigma, low, high = P("mouse.click_hold")
        self._backend.button_event(True)
        self._pacer.tiny(clamp(ln_median(rng, hold_median, hold_sigma), low, high))
        self._backend.button_event(False)

    def idle(self, seconds: float, region: tuple[float, float, float, float] | None = None) -> None:
        """Spend ``seconds`` with the hand on the mouse the way readers do (Huang et al. 2012).

        Mostly the cursor rests (58.8%); sometimes it makes a small examining move (32.9%); rarely
        it traces along a line (2.5%). Rest is pure sleep, which also keeps CPU near zero.
        """
        rng = self._rng
        remaining = seconds
        while remaining > 0.05:
            choice = rng.choices(["park", "examine", "trace"],
                                 weights=[P("mouse.idle_actions")["park"], P("mouse.idle_actions")["examine"],
                                          P("mouse.idle_actions")["trace"]], k=1)[0]
            chunk = min(remaining, rng.uniform(*P("mouse.idle_chunk_s")))
            if choice == "park" or chunk < P("mouse.idle_chunk_s")[0] * 0.8:
                self._pacer.sleep(chunk)
            else:
                x0, y0 = self._backend.position()
                if region:
                    left, top, right, bottom = region
                    tx, ty = rng.uniform(left, right), rng.uniform(top, bottom)
                else:
                    dx, dy = P("mouse.examine_px")
                    tx, ty = x0 + rng.uniform(-dx, dx), y0 + rng.uniform(-dy, dy)
                if choice == "trace":
                    low, high, wobble = P("mouse.trace_px")
                    tx, ty = x0 + rng.uniform(low, high), y0 + rng.uniform(-wobble, wobble)
                start = self._pacer.clock.monotonic()
                self.move(tx, ty, 60, 60)
                spent = self._pacer.clock.monotonic() - start
                self._pacer.sleep(max(0.0, chunk - spent))
            remaining -= chunk
