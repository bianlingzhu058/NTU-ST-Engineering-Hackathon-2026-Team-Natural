"""The between-burst gap mixture has a human shape: CV 1 to 2, bursty, no memory."""
from agent.behaviour.dist import gap_stats
from tests.helpers import kit


def test_gap_mixture_matches_the_human_targets():
    rng, clock, pacer, persona, backend = kit(7)
    stats = gap_stats([pacer.duration("gap") for _ in range(4000)])
    assert 1.0 <= stats["cv"] <= 2.0 and 0.0 <= stats["B"] <= 0.33 and abs(stats["mem"]) < 0.1


def test_klm_mental_operator_is_centred_on_1_35_s():
    rng, clock, pacer, persona, backend = kit(8)
    draws = [pacer.duration("M") for _ in range(5000)]
    assert 1.25 < sum(draws) / len(draws) < 1.45


def test_resumption_lag_grows_with_time_away():
    rng, clock, pacer, persona, backend = kit(9)
    short = sum(pacer.duration("resume", away=3) for _ in range(2000))
    long = sum(pacer.duration("resume", away=120) for _ in range(2000))
    assert long > short


def test_sleep_is_interruptible():
    rng, clock, pacer, persona, backend = kit(1)
    calls = []
    pacer.sleep(30, stop_check=lambda: len(calls) > 2 or calls.append(1))
    assert clock.monotonic() < 2
