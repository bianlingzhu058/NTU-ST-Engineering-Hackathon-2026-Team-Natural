"""Every pacing kind must be clearly non-uniform: coefficient of variation above 0.4."""
import random
from agent.timing import HumanPacer, LognormalDelay


def _cv(values):
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / (len(values) - 1)) ** .5 / mean


def test_lognormal_delays_have_variability():
    assert _cv([LognormalDelay().sample(random.Random(i)) for i in range(300)]) > .4


def test_every_default_kind_has_cv_above_0_4():
    pacer = HumanPacer({}, random.Random(7), sleeper=lambda _: None)
    for kind in ("micro", "step", "read", "think", "gap"):
        samples = [pacer.duration(kind) for _ in range(2000)]
        assert min(samples) > 0
        assert _cv(samples) > .4, kind


def test_fatigue_is_off_by_default():
    pacer = HumanPacer({}, random.Random(0), sleeper=lambda _: None)
    assert pacer._fatigue_factor() == 1.0


def test_fatigue_scales_pauses_up_over_the_session_then_caps():
    clock = [0.0]
    pacer = HumanPacer({"fatigue": {"max": 0.2, "rampup_seconds": 100}},
                       random.Random(0), sleeper=lambda _: None, clock=lambda: clock[0])
    assert abs(pacer._fatigue_factor() - 1.0) < 1e-9     # session start: no drift (keeps tests stable)
    clock[0] = 50.0
    assert abs(pacer._fatigue_factor() - 1.1) < 1e-9     # half the ramp: +10%
    clock[0] = 10_000.0
    assert abs(pacer._fatigue_factor() - 1.2) < 1e-9     # capped at +max


def test_wait_is_sliced_and_interruptible():
    slept = []
    pacer = HumanPacer({"kinds": {"gap": {"median": 5.0, "sigma": 0.1}}}, random.Random(1), sleeper=slept.append)
    pacer.wait("gap", stop_check=lambda: len(slept) >= 3)
    assert len(slept) == 3 and all(0 < s <= 0.25 for s in slept)
