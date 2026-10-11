"""Session scheduling: which task next, and the pause between tasks.

Task choice follows the screen-time shares in Mark et al. 2016 with email removed (browsing 45%,
documents 35%, spreadsheet 20%; ``session.task_weights``), ordered with Barabasi's priority
queue: pending tasks carry random priorities, the highest one runs with probability 0.9, and a
finished task is replaced by a fresh one. That gives natural, slightly bursty ordering instead of
independent dice rolls.

Between tasks the agent waits a draw from the between-burst gap mixture (mostly seconds, one in
five a 20 s to 4 min idle), then pays a resumption lag on the first action of the next task
(Monk 2008). A failed task is logged and the session continues; an AbortRun (the agent lost
track of the desktop) ends the run instead of flailing.
"""
import random
from pathlib import Path
from .behaviour.params import P
from .config import ObjectiveData
from .objectives.yaml_objective import YamlObjective
from .skills.base import AbortRun, SkillError

VERSION = "1.0-research"


class Runner:
    def __init__(self, objectives: list[ObjectiveData], context, dependencies: dict, pacer, rng: random.Random,
                 stop_file: Path, clock=None, min_objective_seconds: float = 75.0):
        self._objectives, self._context, self._dependencies = objectives, context, dependencies
        self._pacer, self._rng, self._stop_file = pacer, rng, stop_file
        self._clock = clock or context.clock
        self._min_objective = min_objective_seconds
        self._queue: list[tuple[float, ObjectiveData]] = []

    def stopped(self) -> bool:
        return self._stop_file.exists()

    def _weight(self, data: ObjectiveData) -> float:
        return float(P("session.task_weights").get(data.name, data.weight))

    def _draw(self, chosen: list[ObjectiveData]) -> ObjectiveData:
        return self._rng.choices(chosen, weights=[max(0.01, self._weight(o)) for o in chosen], k=1)[0]

    def _next(self, chosen: list[ObjectiveData]) -> ObjectiveData:
        """Barabasi 2005 priority queue: highest priority with p = 0.9, otherwise a random one."""
        while len(self._queue) < 3:
            self._queue.append((self._rng.random(), self._draw(chosen)))
        self._queue.sort(key=lambda item: -item[0])
        index = 0 if self._rng.random() < P("session.priority_p") else self._rng.randrange(len(self._queue))
        return self._queue.pop(index)[1]

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
        """Run tasks until the budget is spent or the stop file appears."""
        chosen = [o for o in self._objectives if o.name == objective_name] if objective_name else self._objectives
        if not chosen: raise ValueError(f"No matching objectives: {objective_name}")
        deadline = self._clock.monotonic() + minutes * 60
        self._context.deadline = deadline
        self._pacer.start_session(minutes * 60)
        self._context.logger.log({"event": "run_start", "version": VERSION, "minutes": minutes,
                                  "objective": objective_name or "weighted-priority",
                                  "objectives_available": [o.name for o in chosen],
                                  "persona": self._context.persona.snapshot(),
                                  "desktop_introspection": bool(getattr(self._context.desktop, "available", False)),
                                  "uia": bool(getattr(self._context.uia, "available", False)),
                                  "simulated": bool(getattr(self._context.clock, "virtual", False)),
                                  **self._context.stamp()})
        tasks, reason, away = 0, "budget_reached", 3.0
        try:
            while not self.stopped():
                if self._clock.monotonic() + self._min_objective > deadline:
                    break
                data = self._next(chosen)
                self._context.wait("resume", away=away)
                self._run_objective(data)
                tasks += 1
                if self.stopped() or self._clock.monotonic() + self._min_objective > deadline:
                    break
                away = self._context.wait("gap")
        except AbortRun as exc:
            reason = f"aborted: {exc}"
        if self.stopped(): reason = "stop_file"
        self._context.logger.log({"event": "run_end", "tasks": tasks, "reason": reason,
                                  "elapsed_seconds": round(self._clock.monotonic() - (deadline - minutes * 60), 1),
                                  "actions_logged": self._context.logger.count,
                                  "uia_queries": getattr(self._context.uia, "queries", 0), **self._context.stamp()})

    def run_once(self, objective_name: str) -> None:
        """Execute one named objective for a quick development dry run."""
        matches = [item for item in self._objectives if item.name == objective_name]
        if not matches: raise ValueError(f"No matching objective: {objective_name}")
        self._pacer.start_session(600)
        self._context.logger.log({"event": "run_start", "version": VERSION, "objective": objective_name,
                                  "minutes": None, "persona": self._context.persona.snapshot(),
                                  "simulated": bool(getattr(self._context.clock, "virtual", False)),
                                  "desktop_introspection": bool(getattr(self._context.desktop, "available", False))})
        try:
            self._run_objective(matches[0])
            reason = "single_objective"
        except AbortRun as exc:
            reason = f"aborted: {exc}"
        self._context.logger.log({"event": "run_end", "tasks": 1, "reason": reason,
                                  "actions_logged": self._context.logger.count})
