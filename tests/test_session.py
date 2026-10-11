"""The attention model is what makes the timeline non-stationary rather than merely random."""
import random
from agent.clock import VirtualClock
from agent.session import SessionModel


def _model(seed=4, **kwargs):
    clock = VirtualClock()
    return SessionModel.from_config(kwargs, random.Random(seed), clock), clock


def test_every_attention_state_is_reachable_in_a_long_session():
    model, clock = _model()
    seen = set()
    for _ in range(600):
        clock.sleep(2.0); seen.add(model.step())
    assert seen == {"focused", "steady", "reading", "distracted"}


def test_multiplier_spreads_pauses_but_stays_bounded():
    model, clock = _model()
    values = []
    for _ in range(600):
        clock.sleep(1.5); model.step(); values.append(model.multiplier())
    assert min(values) > 0.2 and max(values) < 8.0
    assert max(values) / min(values) > 2.0  # the pace really does change through the session


def test_fatigue_slows_the_session_down_over_time():
    model, clock = _model(fatigue_per_hour=1.0)
    model.state, model.tempo = "steady", 1.0
    early = model.multiplier()
    clock.sleep(3600)
    assert model.multiplier() > early * 1.9


def test_snapshot_is_what_the_action_log_records():
    model, _ = _model()
    snapshot = model.snapshot()
    assert set(snapshot) == {"attention", "pause_scale"} and snapshot["pause_scale"] > 0
