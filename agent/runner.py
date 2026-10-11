"""Weighted objective selection and bounded scheduling."""
import random
from pathlib import Path
from .config import ObjectiveData
from .objectives.yaml_objective import YamlObjective
from .skills.base import AbortRun, SkillError

VERSION = "0.3-web"


class Runner:
    """Runs randomly selected objectives within a wall-clock budget.

    Between objectives it idles for a "gap" pause (tens of seconds, lognormal), the way a person
    pauses between tasks. A failed objective is logged and the run continues with the next one;
    an AbortRun (the agent has lost track of the desktop) ends the run instead of flailing.
    Each objective is logged as task_start / task_end with its duration, which is the task
    timeline the organisers asked to be able to read.
    """
    def __init__(self, objectives: list[ObjectiveData], context, dependencies: dict, pacer, rng: random.Random,
                 stop_file: Path, clock=None, min_objective_seconds: float = 90.0):
        self._objectives, self._context, self._dependencies = objectives, context, dependencies
        self._pacer, self._rng, self._stop_file = pacer, rng, stop_file
        self._clock = clock or context.clock
        self._min_objective = min_objective_seconds

    def stopped(self) -> bool:
        """True once the operator drops the stop file next to the config folder."""
        return self._stop_file.exists()

    def _run_objective(self, data: ObjectiveData) -> str:
        start = self._clock.monotonic()
        self._context.logger.log({"event": "task_start", "task": data.name})
        status = "completed"
        try:
            YamlObjective(data, self._dependencies).run(self._context, rng=self._rng)
        except SkillError as exc:
            status = f"failed: {exc}"
        except AbortRun as exc:
            status = f"aborted: {exc}"
            raise
        finally:
            self._context.logger.log({"event": "task_end", "task": data.name, "status": status,
                                      "duration_seconds": round(self._clock.monotonic() - start, 1)})
        return status

    def run(self, minutes: float, objective_name: str | None = None) -> None:
        """Select and execute objectives until time expires or the stop file appears."""
        chosen = [o for o in self._objectives if o.name == objective_name] if objective_name else self._objectives
        if not chosen: raise ValueError(f"No matching objectives: {objective_name}")
        deadline = self._clock.monotonic() + minutes * 60
        self._context.deadline = deadline
        self._context.logger.log({"event": "run_start", "version": VERSION, "minutes": minutes,
                                  "objective": objective_name or "weighted-random",
                                  "objectives_available": [o.name for o in chosen],
                                  "desktop_introspection": bool(getattr(self._context.desktop, "available", False)),
                                  "simulated": bool(getattr(self._context.clock, "virtual", False)),
                                  **self._context.stamp()})
        tasks, reason = 0, "budget_reached"
        try:
            while not self.stopped():
                if self._clock.monotonic() + self._min_objective > deadline:
                    break
                data = self._rng.choices(chosen, weights=[max(0.01, o.weight) for o in chosen], k=1)[0]
                self._run_objective(data)
                tasks += 1
                if self.stopped() or self._clock.monotonic() + self._min_objective > deadline:
                    break
                self._pacer.wait("gap", self.stopped)  # between tasks, like getting a coffee
        except AbortRun as exc:
            reason = f"aborted: {exc}"
        if self.stopped(): reason = "stop_file"
        self._context.logger.log({"event": "run_end", "tasks": tasks, "reason": reason,
                                  "elapsed_seconds": round(self._clock.monotonic() - (deadline - minutes * 60), 1),
                                  "actions_logged": self._context.logger.count, **self._context.stamp()})

    def run_once(self, objective_name: str) -> None:
        """Execute one named objective for a quick development dry run."""
        matches = [item for item in self._objectives if item.name == objective_name]
        if not matches: raise ValueError(f"No matching objective: {objective_name}")
        self._context.logger.log({"event": "run_start", "version": VERSION, "objective": objective_name,
                                  "minutes": None, "simulated": bool(getattr(self._context.clock, "virtual", False)),
                                  "desktop_introspection": bool(getattr(self._context.desktop, "available", False))})
        try:
            self._run_objective(matches[0])
            reason = "single_objective"
        except AbortRun as exc:
            reason = f"aborted: {exc}"
        self._context.logger.log({"event": "run_end", "tasks": 1, "reason": reason,
                                  "actions_logged": self._context.logger.count})
