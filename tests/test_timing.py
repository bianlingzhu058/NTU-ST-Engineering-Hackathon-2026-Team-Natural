"""Check deterministic delay samplers remain variable and nonnegative."""
import random
from agent.timing import LognormalDelay


def test_lognormal_delays_have_variability():
    values = [LognormalDelay().sample(random.Random(i)) for i in range(300)]
    mean = sum(values) / len(values)
    cv = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** .5 / mean
    assert cv > .4
