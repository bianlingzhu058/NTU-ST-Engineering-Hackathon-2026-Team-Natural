"""Execution adapter for ordered YAML objective plans.

Plan steps support:
  - skill: name            required
    args: {...}            optional; "{param}" placeholders expand from params;
                           a param that is a list is sampled at random per step
    repeat: [min, max]     optional; run the step a random number of times
    chance: 0.0..1.0       optional; skip the step with probability 1 - chance
    group: name            optional; a run of consecutive steps sharing one group name
                           is executed in a fresh random order each run, so the order
                           of interchangeable actions varies instead of being fixed.
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

    def _choose(self, name: str, options: list, rng: random.Random) -> Any:
        """Pick from a list at random, but avoid repeating the previous pick for this param
        back to back, so the same site (or find term) is never used twice in a row. A site
        can still recur later in the run, the way a person revisits a page."""
        pick = rng.choice(options)
        if len(options) > 1:
            tries = 0
            while pick == self._last_pick.get(name) and tries < 5:
                pick = rng.choice(options); tries += 1
        self._last_pick[name] = pick
        return pick

    def _expand(self, value: Any, params: dict[str, Any], rng: random.Random) -> Any:
        if isinstance(value, dict): return {k: self._expand(v, params, rng) for k, v in value.items()}
        if isinstance(value, list): return [self._expand(v, params, rng) for v in value]
        if isinstance(value, str):
            whole = re.fullmatch(r"\{([\w_]+)\}", value)
            if whole and whole.group(1) in params:  # whole-value placeholder keeps lists as lists
                name = whole.group(1); chosen = params[name]
                if isinstance(chosen, list) and chosen and not isinstance(chosen[0], list):
                    return self._choose(name, chosen, rng)
                return chosen
            def sub(m):
                name = m.group(1); chosen = params.get(name, m.group(0))
                if isinstance(chosen, list) and chosen:
                    return str(self._choose(name, chosen, rng))
                return str(chosen)
            return re.sub(r"\{([\w_]+)\}", sub, value)
        return value

    def _run_step(self, step: dict, context: Any, rng: random.Random) -> None:
        if rng.random() >= float(step.get("chance", 1.0)): return
        lo, hi = step.get("repeat", [1, 1])
        for _ in range(rng.randint(int(lo), int(hi))):
            args = self._expand(dict(step.get("args", {}) or {}), self.data.params, rng)
            create_skill(step["skill"], **self.skill_dependencies).run(context, args)
            if context.pacer: context.pacer.wait("step")

    def run(self, context: Any, *, rng: random.Random | None = None) -> None:
        """Execute plan steps in order with pauses between them.

        A run of consecutive steps that share a ``group`` name is shuffled first, so
        interchangeable actions (e.g. hover / scroll / find on a page) happen in a
        different order each run. Ungrouped steps keep their written order.
        """
        rng = rng or random.Random()
        self._last_pick: dict[str, Any] = {}   # last value chosen per list param (no back-to-back repeats)
        steps = self.data.plan
        i = 0
        while i < len(steps):
            group = steps[i].get("group")
            if group is not None:
                block = [steps[i]]
                j = i + 1
                while j < len(steps) and steps[j].get("group") == group:
                    block.append(steps[j]); j += 1
                rng.shuffle(block)
                for member in block: self._run_step(member, context, rng)
                i = j
            else:
                self._run_step(steps[i], context, rng); i += 1
