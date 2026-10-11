import random
from agent.behaviour.persona import Persona
from agent.clock import VirtualClock
from agent.input.fake_backend import FakeInputBackend
from agent.timing import Pacer


def kit(seed: int = 1):
    rng, clock = random.Random(seed), VirtualClock()
    return rng, clock, Pacer(rng, clock=clock), Persona.sample(random.Random(seed)), FakeInputBackend()
