"""Every pause the agent takes, drawn from the research distributions in behaviour/params.py.

Two kinds of waiting exist and are kept apart:

  behaviour  how long a person takes: KLM mental preparation before a command, resumption lag
             after switching, the between-burst gap mixture, page and screen dwell. Each named
             kind maps to one cited distribution (see KIND_SOURCES).
  polling    how often the agent looks at the window title while waiting for an app or a page.
             That is perception, not behaviour; it is short, jittered and never logged.

Nothing here sleeps for a constant. ``sleep`` is sliced so the stop file and the hotkey are
honoured within a quarter of a second, and every behaviour sample is recorded so the simulator
and tests can check the shape of the timeline.
"""
import math
import random
from .behaviour.dist import clamp, ln_mean, ln_median, trunc_pareto
from .behaviour.params import P
from .clock import RealClock

KIND_SOURCES = {
    "M": "klm.M (Card, Moran and Newell 1980)",
    "H": "klm.H (Card, Moran and Newell 1980)",
    "click": "web.click_composite_s (Sauro) minus pointing time",
    "resume": "resume.* (Monk, Trafton and Boehm-Davis 2008)",
    "gap": "gap.* (Barabasi 2005, Dezso 2006, Halfaker 2015 anchored mixture)",
    "focus": "focus.* (Mark et al. 2016)",
}


class Pacer:
    """Samples and performs human pauses; holds the run's elapsed fraction for drift."""
    def __init__(self, rng: random.Random, sleeper=None, clock=None):
        self.clock = clock or RealClock()
        self._rng, self._sleeper = rng, sleeper or self.clock.sleep
        self.samples: list[tuple[str, float]] = []
        self._start, self._total = self.clock.monotonic(), 900.0
        self.last_switch = self.clock.monotonic()

    def start_session(self, total_seconds: float) -> None:
        self._start, self._total = self.clock.monotonic(), max(1.0, total_seconds)

    def elapsed_fraction(self) -> float:
        return clamp((self.clock.monotonic() - self._start) / self._total, 0.0, 1.0)

    # sampling
    def duration(self, kind: str, **kw) -> float:
        rng = self._rng
        if kind == "M":
            return ln_mean(rng, P("klm.M"), P("klm.sigma"))
        if kind == "H":
            return ln_mean(rng, P("klm.H"), P("klm.sigma"))
        if kind == "click":
            # Sauro's 3.73 s covers perceiving, deciding and pointing. Pointing is timed separately by
            # Fitts's law in the mouse model, so only the decision part is waited here.
            return max(0.3, ln_mean(rng, P("web.click_composite_s") - P("klm.P"), P("klm.sigma")))
        if kind == "resume":
            away = max(1.0, float(kw.get("away", 3.0)))
            mean_ms = P("resume.a_ms") + P("resume.b_ms") * math.log(away)
            return ln_mean(rng, mean_ms / 1000.0, P("resume.sigma"))
        if kind == "gap":
            idle_w = P("gap.idle_weight") * (1 + P("gap.idle_drift") * self.elapsed_fraction())
            if rng.random() < idle_w:
                low, high = P("gap.idle_range_s")
                return trunc_pareto(rng, low, P("gap.idle_alpha"), high)
            return ln_median(rng, P("gap.lognormal_median_s"), P("gap.lognormal_sigma"))
        if kind == "focus":
            return ln_median(rng, P("focus.median_s"), P("focus.sigma"))
        if kind == "poll":
            return rng.uniform(*P("system.poll_s"))
        raise KeyError(f"unknown pause kind: {kind}")

    def wait(self, kind: str, stop_check=lambda: False, **kw) -> float:
        """Sample a behaviour pause of ``kind`` and sleep it. Returns the seconds waited."""
        seconds = self.duration(kind, **kw)
        if kind != "poll": self.samples.append((kind, seconds))
        self.sleep(seconds, stop_check)
        return seconds

    def sleep(self, seconds: float, stop_check=lambda: False) -> None:
        """Sleep in short slices so a stop request is honoured quickly."""
        remaining = max(0.0, seconds)
        while remaining > 0 and not stop_check():
            chunk = remaining if remaining <= 0.25 else self._rng.uniform(0.15, 0.25)
            self._sleeper(chunk)
            remaining -= chunk

    def tiny(self, seconds: float) -> None:
        """A sub-second motor interval (key, notch, mouse step); not sliced, not recorded."""
        if seconds > 0: self._sleeper(seconds)
