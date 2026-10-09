"""Probability-based pacing isolated from skill and input logic."""
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


class HumanPacer:
    """Chooses configured delay strategies and performs interruptible waits."""
    def __init__(self, settings: dict, rng: random.Random, sleeper=time.sleep):
        self._settings, self._rng, self._sleeper = settings, rng, sleeper
        self.samples: list[tuple[str, float]] = []
        base = LognormalDelay(settings.get("lognormal_mu", -0.4), settings.get("lognormal_sigma", 0.65))
        self._read = CompositeDelay(base, settings.get("long_pause_probability", .04), *settings.get("long_pause_seconds", [2., 7.]))

    def duration(self, kind: str) -> float:
        """Sample a duration for a pacing category."""
        if kind == "read": return self._read.sample(self._rng)
        low, high = self._settings.get(f"{kind}_seconds", [0.1, 0.4])
        return UniformDelay(low, high).sample(self._rng)

    def wait(self, kind: str, stop_check=lambda: False) -> None:
        """Wait in short interruptible slices using sampled durations."""
        remaining = self.duration(kind)
        self.samples.append((kind, remaining))
        while remaining > 0 and not stop_check():
            slice_seconds = min(remaining, self._rng.uniform(.05, .2))
            self._sleeper(slice_seconds)
            remaining -= slice_seconds
