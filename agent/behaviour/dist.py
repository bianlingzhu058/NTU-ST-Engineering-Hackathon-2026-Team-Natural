"""Samplers for the distributions the behaviour research calls for, stdlib ``random`` only."""
import math
import random


def ln_mean(rng: random.Random, mean: float, sigma: float) -> float:
    """Lognormal with expected value ``mean`` (used where a paper reports a mean)."""
    return rng.lognormvariate(math.log(max(mean, 1e-9)) - sigma * sigma / 2, sigma)


def ln_median(rng: random.Random, median: float, sigma: float) -> float:
    """Lognormal with median ``median`` (used where a paper reports a median)."""
    return rng.lognormvariate(math.log(max(median, 1e-9)), sigma)


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def weibull(rng: random.Random, shape: float, scale: float) -> float:
    """Weibull draw; note ``random.weibullvariate`` takes scale first."""
    return rng.weibullvariate(scale, shape)


def trunc_pareto(rng: random.Random, xmin: float, alpha: float, xmax: float) -> float:
    """Truncated Pareto by inverse CDF; ``alpha`` is the survival exponent."""
    u = rng.random()
    a, b = xmin ** -alpha, xmax ** -alpha
    return (a - u * (a - b)) ** (-1 / alpha)


def weighted(rng: random.Random, options: dict) -> str:
    """Pick a key of ``options`` with probability proportional to its value."""
    keys = list(options)
    return rng.choices(keys, weights=[max(0.0, float(options[k])) for k in keys], k=1)[0]


def gap_stats(gaps: list[float]) -> dict:
    """CV, burstiness B = (sd - mean) / (sd + mean) and lag-1 memory of a gap series."""
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
            "B": (sd - mean) / (sd + mean) if sd + mean else 0.0, "mem": mem}
