"""Execution adapter for ordered YAML objective plans.

Plan steps support:
  - skill: name            required
    args: {...}            optional; "{param}" placeholders expand from params;
                           a param that is a list is sampled at random per step
    repeat: [min, max]     optional; run the step a random number of times
    chance: 0.0..1.0       optional; skip the step with probability 1 - chance
A human-scale "step" pause is taken between plan steps.
"""
from dataclasses import dataclass
import random
import re
from typing import Any
from ..config import ObjectiveData
from ..interfaces import Objective
from ..registry import create_skill


@dataclass
class YamlObjective(Objective):
    """Expands objective parameters and runs its registered skill calls."""
    data: ObjectiveData
    skill_dependencies: dict[str, Any]
    @property
    def name(self) -> str: return self.data.name
    @property
    def weight(self) -> float: return self.data.weight

    def _expand(self, value: Any, params: dict[str, Any], rng: random.Random) -> Any:
        if isinstance(value, dict): return {k: self._expand(v, params, rng) for k, v in value.items()}
        if isinstance(value, list): return [self._expand(v, params, rng) for v in value]
        if isinstance(value, str):
            whole = re.fullmatch(r"\{([\w_]+)\}", value)
            if whole and whole.group(1) in params:  # whole-value placeholder keeps lists as lists
                chosen = params[whole.group(1)]
                return rng.choice(chosen) if isinstance(chosen, list) and chosen and not isinstance(chosen[0], list) else chosen
            def sub(m):
                chosen = params.get(m.group(1), m.group(0))
                return str(rng.choice(chosen) if isinstance(chosen, list) and chosen else chosen)
            return re.sub(r"\{([\w_]+)\}", sub, value)
        return value

    def run(self, context: Any, *, rng: random.Random | None = None) -> None:
        """Execute plan steps in order with pauses between them."""
        rng = rng or random.Random()
        for index, step in enumerate(self.data.plan):
            if rng.random() >= float(step.get("chance", 1.0)): continue
            lo, hi = step.get("repeat", [1, 1])
            for _ in range(rng.randint(int(lo), int(hi))):
                args = self._expand(dict(step.get("args", {}) or {}), self.data.params, rng)
                create_skill(step["skill"], **self.skill_dependencies).run(context, args)
                if context.pacer: context.pacer.wait("step")
