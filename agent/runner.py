"""Weighted objective selection and bounded scheduling."""
import random
import time
from pathlib import Path
from typing import Callable
from .config import ObjectiveData
from .objectives.yaml_objective import YamlObjective
from .skills.base import SkillError


class Runner:
    """Runs randomly selected objectives within a wall-clock budget.

    Between objectives it idles for a "gap" pause (tens of seconds, lognormal),
    the way a person pauses between tasks. A failed objective is logged and the
    run continues with the next one. Logging per objective gives the task
    timeline (task, start, end, duration) the organisers asked to see.
    """
    def __init__(self, objectives: list[ObjectiveData], context, dependencies: dict, pacer, rng: random.Random,
                 stop_file: Path, clock: Callable[[], float] = time.monotonic):
        self._objectives, self._context, self._dependencies = objectives, context, dependencies
        self._pacer, self._rng, self._stop_file, self._clock = pacer, rng, stop_file, clock

    def _stopped(self) -> bool: return self._stop_file.exists()

    def _run_objective(self, data: ObjectiveData) -> None:
        start = self._clock()
        self._context.logger.log({"event": "task_start", "task": data.name})
        try:
            YamlObjective(data, self._dependencies).run(self._context, rng=self._rng)
            status = "completed"
        except SkillError as exc:
            status = f"failed: {exc}"
        self._context.logger.log({"event": "task_end", "task": data.name, "status": status,
                                  "duration_seconds": round(self._clock() - start, 1)})

    def run(self, minutes: float, objective_name: str | None = None) -> None:
        """Select and execute objectives until time expires or the stop file appears."""
        chosen = [o for o in self._objectives if o.name == objective_name] if objective_name else self._objectives
        if not chosen: raise ValueError(f"No matching objectives: {objective_name}")
        deadline = self._clock() + minutes * 60
        self._context.logger.log({"event": "run_start", "minutes": minutes, "objective": objective_name})
        while self._clock() < deadline and not self._stopped():
            data = self._rng.choices(chosen, weights=[max(0.01, o.weight) for o in chosen], k=1)[0]
            self._run_objective(data)
            if self._clock() < deadline and not self._stopped(): self._pacer.wait("gap", self._stopped)
        self._context.logger.log({"event": "run_end", "stopped_by_file": self._stopped()})

    def run_once(self, objective_name: str) -> None:
        """Execute one named objective for a quick development dry run."""
        matches = [item for item in self._objectives if item.name == objective_name]
        if not matches: raise ValueError(f"No matching objective: {objective_name}")
        self._run_objective(matches[0])
