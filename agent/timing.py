"""Probability-based pacing isolated from skill and input logic.

Every wait in the agent comes through ``HumanPacer.wait(kind)``. Each kind is
a lognormal distribution (configured by median and sigma) optionally mixed
with occasional long pauses, so no pause category is ever uniform or fixed.
"""
from dataclasses import dataclass
import random
import time
from .interfaces import DelayDistribution


@dataclass
class LognormalDelay(DelayDistribution):
    """Samples positive durations from a lognormal distribution."""
    mu: float = -0.4
    sigma: float = 0.65
    def sample(self, rng: random.Random) -> float: return rng.lognormvariate(self.mu, self.sigma)

    @classmethod
    def from_median(cls, median: float, sigma: float) -> "LognormalDelay":
        import math
        return cls(math.log(max(median, 1e-3)), sigma)


@dataclass
class GaussianDelay(DelayDistribution):
    """Samples nonnegative durations from a Gaussian distribution."""
    mean: float = 0.3
    sigma: float = 0.1
    def sample(self, rng: random.Random) -> float: return max(0.0, rng.gauss(self.mean, self.sigma))


@dataclass
class UniformDelay(DelayDistribution):
    """Samples durations uniformly from a bounded interval."""
    low: float = 0.1
    high: float = 0.5
    def sample(self, rng: random.Random) -> float: return rng.uniform(self.low, self.high)


@dataclass
class CompositeDelay(DelayDistribution):
    """Adds occasional long pauses to a base duration strategy."""
    base: DelayDistribution
    probability: float = 0.04
    long_low: float = 2.0
    long_high: float = 7.0
    def sample(self, rng: random.Random) -> float:
        return rng.uniform(self.long_low, self.long_high) if rng.random() < self.probability else self.base.sample(rng)


@dataclass
class ClampedDelay(DelayDistribution):
    """Caps another distribution to a hard [minimum, maximum] range. Used for the between-objective
    switch in demo mode, where a firm ceiling (e.g. 15 s) keeps the pacing crisp on camera while the
    base is still a varied, non-fixed draw."""
    base: DelayDistribution
    maximum: float
    minimum: float = 0.0
    def sample(self, rng: random.Random) -> float:
        return max(self.minimum, min(self.maximum, self.base.sample(rng)))


@dataclass
class GapMixtureDelay(DelayDistribution):
    """Between-burst gap as a two-component mixture: mostly a short 'within-screen'
    lognormal, sometimes a heavy-tailed idle pause (truncated Pareto).

    This is the research-grounded shape for the gaps the judges actually score — the
    intervals between Sysmon/Procmon event bursts. A single lognormal (our old `gap`,
    sigma 0.5) has CV ~0.5, which is MORE regular than a random Poisson process
    (CV = 1) and reads as a bot. The heavy idle tail lifts the coefficient of
    variation into the human band (CV ~1.5, burstiness B > 0, no memory between
    gaps). Anchored to Barabasi 2005, Dezso 2006 and Halfaker 2015; mixture weights
    are design values checked by tests/test_gap_shape.py.
    """
    median: float = 8.0          # within-screen lognormal gap median (seconds)
    sigma: float = 0.9
    idle_weight: float = 0.20    # share of gaps drawn from the heavy idle tail
    idle_low: float = 20.0       # truncated-Pareto lower bound (seconds)
    idle_high: float = 240.0     # truncated-Pareto upper bound (seconds)
    idle_alpha: float = 0.2      # truncated-Pareto survival exponent (smaller = heavier tail)
    def sample(self, rng: random.Random) -> float:
        import math
        if rng.random() < self.idle_weight:
            u = rng.random()
            a, b = self.idle_low ** -self.idle_alpha, self.idle_high ** -self.idle_alpha
            return (a - u * (a - b)) ** (-1.0 / self.idle_alpha)   # inverse-CDF truncated Pareto
        return rng.lognormvariate(math.log(max(self.median, 1e-3)), self.sigma)


def gap_stats(gaps: list) -> dict:
    """Coefficient of variation, burstiness B = (sd-mean)/(sd+mean) and lag-1 memory
    of a gap series — the statistics the judges compute on the burst-gap series.
    Human target: CV 1 to 2, B 0 to 0.33, |memory| < 0.15 (Goh and Barabasi 2008)."""
    import math
    n = len(gaps)
    if n < 3: return {"n": n}
    mean = sum(gaps) / n
    sd = math.sqrt(sum((g - mean) ** 2 for g in gaps) / n)
    a, b = gaps[:-1], gaps[1:]
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va, vb = sum((x - ma) ** 2 for x in a), sum((y - mb) ** 2 for y in b)
    mem = cov / math.sqrt(va * vb) if va > 0 and vb > 0 else 0.0
    return {"n": n, "mean": mean, "sd": sd, "cv": sd / mean if mean else 0.0,
            "B": (sd - mean) / (sd + mean) if (sd + mean) else 0.0, "mem": mem}


DEFAULT_KINDS = {  # median seconds, sigma, long-pause probability, long-pause range
    "micro": {"median": 0.09, "sigma": 0.45},
    "step": {"median": 0.45, "sigma": 0.55, "long_probability": 0.03, "long_seconds": [1.5, 4.0]},
    "read": {"median": 2.5, "sigma": 0.6, "long_probability": 0.15, "long_seconds": [4.0, 9.0]},
    "think": {"median": 1.2, "sigma": 0.6, "long_probability": 0.10, "long_seconds": [3.0, 8.0]},
    "burst": {"median": 2.5, "sigma": 0.55, "long_probability": 0.08, "long_seconds": [6.0, 10.0]},
    "para": {"median": 8.0, "sigma": 0.40, "long_probability": 0.08, "long_seconds": [12.0, 15.0]},
    "cell": {"median": 0.8, "sigma": 0.55, "long_probability": 0.14, "long_seconds": [2.0, 4.0]},
    "keydata": {"median": 0.20, "sigma": 0.50, "long_probability": 0.05, "long_seconds": [0.5, 0.9]},
    "switch": {"median": 10.0, "sigma": 0.50, "long_probability": 0.10, "long_seconds": [25.0, 45.0]},
    # Between-task gap now uses the research mixture (CV ~1.5) instead of a single
    # lognormal (CV ~0.5). This is the gap series the judges score.
    "gap": {"mixture": True, "median": 8.0, "sigma": 0.9,
            "idle_weight": 0.20, "idle_range": [20.0, 240.0], "idle_alpha": 0.2},
}


class HumanPacer:
    """Chooses configured delay strategies and performs interruptible waits."""
    def __init__(self, settings: dict, rng: random.Random, sleeper=time.sleep, clock=time.monotonic):
        self._rng, self._sleeper, self._clock = rng, sleeper, clock
        self.samples: list[tuple[str, float]] = []
        self._global_stop = lambda: False   # checked inside EVERY wait so Stop halts mid-skill
        # Session fatigue: people slow down over a long session. Every sampled pause is scaled
        # by 1 .. 1+max as wall-clock time passes (peak reached after rampup_seconds), adding a
        # slow human drift across the whole timeline. It is ~1.0 at session start, so pauses
        # sampled immediately (the unit tests) are unaffected. max=0 disables it entirely.
        fat = settings.get("fatigue") or {}
        self._fatigue_max = max(0.0, float(fat.get("max", 0.0)))
        self._fatigue_ramp = max(1.0, float(fat.get("rampup_seconds", 1200.0)))
        self._t0 = clock()
        self._kinds: dict[str, DelayDistribution] = {}
        merged = {**DEFAULT_KINDS, **(settings.get("kinds") or {})}
        for kind, spec in merged.items():
            if spec.get("mixture"):
                low, high = spec.get("idle_range", [20.0, 240.0])
                self._kinds[kind] = GapMixtureDelay(
                    float(spec.get("median", 8.0)), float(spec.get("sigma", 0.9)),
                    float(spec.get("idle_weight", 0.20)), float(low), float(high),
                    float(spec.get("idle_alpha", 0.2)))
                continue
            base = LognormalDelay.from_median(float(spec.get("median", 0.5)), float(spec.get("sigma", 0.5)))
            if spec.get("long_probability"):
                low, high = spec.get("long_seconds", [2.0, 6.0])
                base = CompositeDelay(base, float(spec["long_probability"]), float(low), float(high))
            if spec.get("max") is not None:   # hard ceiling (e.g. the demo-mode switch capped at 15s)
                base = ClampedDelay(base, float(spec["max"]), float(spec.get("min", 0.0)))
            self._kinds[kind] = base

    def set_stop(self, stop_check) -> None:
        """Register a global stop predicate (e.g. the stop-file check) checked inside every
        wait slice, so a Stop request halts within ~0.25 s even mid-skill, not only between
        objectives."""
        self._global_stop = stop_check or (lambda: False)

    def _fatigue_factor(self) -> float:
        """1.0 at session start, ramping to 1+max after rampup_seconds of wall-clock time."""
        if self._fatigue_max <= 0.0:
            return 1.0
        elapsed = max(0.0, self._clock() - self._t0)
        return 1.0 + self._fatigue_max * min(1.0, elapsed / self._fatigue_ramp)

    def duration(self, kind: str) -> float:
        """Sample a duration for a pacing category, scaled by the current session fatigue."""
        return self._kinds.get(kind, self._kinds["step"]).sample(self._rng) * self._fatigue_factor()

    def wait(self, kind: str, stop_check=lambda: False) -> None:
        """Wait in short interruptible slices using sampled durations."""
        remaining = self.duration(kind)
        self.samples.append((kind, remaining))
        stop = lambda: stop_check() or self._global_stop()
        while remaining > 0 and not stop():
            slice_seconds = min(remaining, self._rng.uniform(.05, .25))
            self._sleeper(slice_seconds)
            remaining -= slice_seconds
