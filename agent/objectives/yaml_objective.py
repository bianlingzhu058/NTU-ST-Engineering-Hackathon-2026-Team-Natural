"""Execution adapter for ordered YAML objective plans.

Plan steps support:
  - skill: name            a registered skill
    args: {...}            "{param}" placeholders expand from params; a param that is a list
                           is sampled at random per step
    repeat: [min, max]     run the step a random number of times
    chance: 0.0..1.0       skip the step with probability 1 - chance
  - group: [steps]         a nested block, so "visit a site" (navigate, read, maybe follow a
    repeat: [min, max]     link) can repeat as a unit a random number of times
    min_time_left: 60      stop repeating the block when less than this many seconds of the
                           run budget remain, so the closing steps still get to run

A human-scale "step" pause is taken between plan steps, and the stop file is honoured between
them too, so an abort never lands in the middle of an action.
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
            def sub(match):
                chosen = params.get(match.group(1), match.group(0))
                return str(rng.choice(chosen) if isinstance(chosen, list) and chosen else chosen)
            return re.sub(r"\{([\w_]+)\}", sub, value)
        return value

    def _run_step(self, context: Any, step: dict, rng: random.Random) -> None:
        if rng.random() >= float(step.get("chance", 1.0)): return
        low, high = step.get("repeat", [1, 1])
        for index in range(rng.randint(int(low), int(high))):
            if context.stop_check(): return
            if "group" in step:
                if index and context.time_left() < float(step.get("min_time_left", 60)): return
                for inner in step["group"]:
                    self._run_step(context, inner, rng)
                continue
            args = self._expand(dict(step.get("args", {}) or {}), self.data.params, rng)
            create_skill(step["skill"], **self.skill_dependencies).run(context, args)
            if context.pacer: context.wait("step")

    def run(self, context: Any, *, rng: random.Random | None = None) -> None:
        """Execute plan steps in order with pauses between them."""
        rng = rng or random.Random()
        for step in self.data.plan:
            if context.stop_check(): return
            self._run_step(context, step, rng)
