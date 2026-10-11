"""Probability-based pacing, isolated from skill and input logic.

Every wait in the agent comes through ``HumanPacer.wait(kind)``. Each kind is a lognormal
distribution (configured by median and sigma) mixed with occasional long pauses, scaled by the
session's attention multiplier and clamped to a sane maximum so one unlucky draw cannot eat the
run budget. Nothing anywhere in the agent sleeps for a constant.

The lognormal shape is the point: it is right-skewed, so most gaps are short and a few are much
longer, which is what a Process Monitor timeline of a real person looks like. The coefficient of
variation of every kind is asserted above 0.4 in tests/test_timing.py, and the end-to-end CV of
the action timeline is asserted in tests/test_simulation.py.
"""
from dataclasses import dataclass
import random
from .clock import RealClock
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


DEFAULT_KINDS = {  # median seconds, sigma, long-pause probability and range, hard cap
    "micro": {"median": 0.09, "sigma": 0.45, "max_seconds": 1.5},
    "step": {"median": 0.45, "sigma": 0.55, "long_probability": 0.03, "long_seconds": [1.5, 4.0], "max_seconds": 10.0},
    "read": {"median": 2.5, "sigma": 0.60, "long_probability": 0.15, "long_seconds": [4.0, 9.0], "max_seconds": 30.0},
    "think": {"median": 1.2, "sigma": 0.60, "long_probability": 0.10, "long_seconds": [3.0, 8.0], "max_seconds": 25.0},
    "gap": {"median": 14.0, "sigma": 0.50, "long_probability": 0.10, "long_seconds": [25.0, 50.0], "max_seconds": 90.0},
}
FLOOR_SECONDS = 0.015


class HumanPacer:
    """Chooses configured delay strategies and performs interruptible waits."""
    def __init__(self, settings: dict, rng: random.Random, sleeper=None, modulator=None, clock=None):
        clock = clock or RealClock()
        self._rng, self._sleeper, self._modulator = rng, sleeper or clock.sleep, modulator
        self.samples: list[tuple[str, float]] = []
        self._kinds: dict[str, DelayDistribution] = {}
        self._caps: dict[str, float] = {}
        merged = {**DEFAULT_KINDS, **(settings.get("kinds") or {})}
        for kind, spec in merged.items():
            base = LognormalDelay.from_median(float(spec.get("median", 0.5)), float(spec.get("sigma", 0.5)))
            if spec.get("long_probability"):
                low, high = spec.get("long_seconds", [2.0, 6.0])
                base = CompositeDelay(base, float(spec["long_probability"]), float(low), float(high))
            self._kinds[kind] = base
            self._caps[kind] = float(spec.get("max_seconds", 60.0))

    def duration(self, kind: str) -> float:
        """Sample a duration for a pacing category, scaled by the session and capped."""
        distribution = self._kinds.get(kind) or self._kinds["step"]
        scale = self._modulator() if self._modulator else 1.0
        raw = distribution.sample(self._rng) * max(0.05, scale)
        return min(max(raw, FLOOR_SECONDS), self._caps.get(kind, 60.0))

    def wait(self, kind: str, stop_check=lambda: False) -> None:
        """Wait in short interruptible slices using sampled durations."""
        remaining = self.duration(kind)
        self.samples.append((kind, remaining))
        while remaining > 0 and not stop_check():
            slice_seconds = min(remaining, self._rng.uniform(.05, .25))
            self._sleeper(slice_seconds)
            remaining -= slice_seconds
