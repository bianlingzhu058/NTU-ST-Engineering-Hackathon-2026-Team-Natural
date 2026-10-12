"""The between-task gap series must have a human shape, not a bot's.

The judges score the gaps between Sysmon/Procmon event bursts. Humans are bursty:
coefficient of variation (CV) 1 to 2, burstiness B > 0, and almost no correlation
between consecutive gaps (Goh and Barabasi 2008; Mark 2005 field CV 1.6 to 2.2).
A single lognormal (our old `gap`) sat near CV 0.5 — MORE regular than a random
Poisson process (CV = 1), which is exactly the signature a bot detector keys on.
This test fails if the gap kind ever regresses to that regime.
"""
import random
from agent.timing import HumanPacer, GapMixtureDelay, gap_stats


def _gap_series(n=4000, seed=7):
    pacer = HumanPacer({}, random.Random(seed), sleeper=lambda _: None)
    return [pacer.duration("gap") for _ in range(n)]


def test_default_gap_lands_in_the_human_band():
    s = gap_stats(_gap_series())
    assert 1.0 <= s["cv"] <= 2.0, f"CV {s['cv']:.2f} outside human band 1-2"
    assert 0.0 <= s["B"] <= 0.40, f"burstiness B {s['B']:.2f} not heavy-tailed"
    assert abs(s["mem"]) < 0.15, f"lag-1 memory {s['mem']:.3f} too high (gaps must be ~independent)"


def test_gap_is_the_mixture_strategy_not_a_plain_lognormal():
    pacer = HumanPacer({}, random.Random(1), sleeper=lambda _: None)
    assert isinstance(pacer._kinds["gap"], GapMixtureDelay)


def test_gap_median_is_short_but_mean_is_pulled_up_by_the_idle_tail():
    """The heavy idle tail is what creates the burstiness: median stays ~8-11 s while
    the mean is dragged well above it by rare long idle pauses."""
    s = gap_stats(sorted(_gap_series()))
    series = sorted(_gap_series())
    median = series[len(series) // 2]
    assert 5.0 < median < 15.0, f"median {median:.1f}s off"
    assert s["mean"] > median, "mean should exceed median (right-skewed, heavy tail)"
