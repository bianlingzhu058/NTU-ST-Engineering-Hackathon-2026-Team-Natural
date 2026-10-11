"""The attention model behind "do the delays follow a realistic curve?".

Drawing every pause from one fixed distribution already beats fixed sleeps, but it produces a
*stationary* timeline: the average pace at minute 1 is the average pace at minute 14. Real
sessions do not look like that. A person skims fast for a while, settles into reading, gets
distracted, comes back slower than they started.

So the pause scale is modulated by three things, all cheap and all visible in the log:
  1. an attention state from a small Markov chain (focused, steady, reading, distracted),
  2. a slow random walk on tempo, so the pace drifts inside a state as well,
  3. fatigue, a mild monotone slowdown across the run.

Every pause in the agent is multiplied by ``multiplier()``, which is why the inter-action gap
distribution comes out both wide (high coefficient of variation) and non-stationary.
"""
from dataclasses import dataclass, field
import math
import random

DEFAULT_STATES = {"focused": 0.65, "steady": 1.0, "reading": 1.7, "distracted": 3.1}
DEFAULT_TRANSITIONS = {
    "focused": {"focused": .62, "steady": .30, "reading": .06, "distracted": .02},
    "steady": {"focused": .16, "steady": .60, "reading": .19, "distracted": .05},
    "reading": {"focused": .06, "steady": .30, "reading": .56, "distracted": .08},
    "distracted": {"focused": .12, "steady": .46, "reading": .30, "distracted": .12},
}


@dataclass
class SessionModel:
    """Holds the current attention state and turns it into a pause multiplier."""
    rng: random.Random
    clock: object = None
    states: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_STATES))
    transitions: dict[str, dict[str, float]] = field(default_factory=lambda: {k: dict(v) for k, v in DEFAULT_TRANSITIONS.items()})
    fatigue_per_hour: float = 0.35
    walk_sigma: float = 0.09
    walk_bounds: tuple[float, float] = (0.6, 1.7)
    state: str = "steady"
    tempo: float = 1.0
    transitions_taken: int = 0

    @classmethod
    def from_config(cls, settings: dict, rng: random.Random, clock=None) -> "SessionModel":
        """Build from the ``session`` config section; an empty section gives the defaults."""
        states = {**DEFAULT_STATES, **(settings.get("states") or {})}
        transitions = {k: {**DEFAULT_TRANSITIONS.get(k, {}), **(v or {})}
                       for k, v in {**DEFAULT_TRANSITIONS, **(settings.get("transitions") or {})}.items()}
        start = settings.get("start_state") or rng.choice(sorted(states))
        return cls(rng, clock, states, transitions, float(settings.get("fatigue_per_hour", 0.35)),
                   float(settings.get("walk_sigma", 0.09)), state=start if start in states else "steady")

    def _fatigue(self) -> float:
        elapsed = self.clock.monotonic() if self.clock is not None else 0.0
        return 1.0 + self.fatigue_per_hour * max(0.0, elapsed) / 3600.0

    def multiplier(self) -> float:
        """Current pause scale: attention state times drifting tempo times fatigue."""
        return self.states.get(self.state, 1.0) * self.tempo * self._fatigue()

    def step(self) -> str:
        """Advance one macro action: drift the tempo and maybe change attention state."""
        low, high = self.walk_bounds
        self.tempo = min(high, max(low, self.tempo * math.exp(self.rng.gauss(0.0, self.walk_sigma))))
        options = self.transitions.get(self.state) or {self.state: 1.0}
        names = sorted(options)
        nxt = self.rng.choices(names, weights=[max(0.0, options[n]) for n in names], k=1)[0]
        if nxt != self.state:
            self.state, self.transitions_taken = nxt, self.transitions_taken + 1
        return self.state

    def snapshot(self) -> dict:
        """What the action log records about the session's rhythm at this moment."""
        return {"attention": self.state, "pause_scale": round(self.multiplier(), 2)}
