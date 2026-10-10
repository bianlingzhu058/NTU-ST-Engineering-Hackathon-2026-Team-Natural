"""Weighted objective selection and bounded scheduling."""
import random
import time
from pathlib import Path
from typing import Callable
from .config import ObjectiveData
from .objectives.yaml_objective import YamlObjective
from .run_control import RunControl, RunStopped


class Runner:
    """Runs randomly selected objectives within a wall-clock budget."""
    def __init__(self, objectives: list[ObjectiveData], context, dependencies: dict, pacer, rng: random.Random,
                 stop_file: Path, clock: Callable[[], float] = time.monotonic,
                 control: RunControl | None = None, progress_callback=None):
        self._objectives, self._context, self._dependencies = objectives, context, dependencies
        self._pacer, self._rng, self._stop_file, self._clock = pacer, rng, stop_file, clock
        self.control = control or RunControl(stop_file.exists)
        self.current_scenario: str | None = None
        self.current_skill: str | None = None
        self.progress_callback = progress_callback
        self._context.progress_callback = self._report_progress

    def _report_progress(self, scenario: str, skill: str) -> None:
        self.current_scenario, self.current_skill = scenario, skill
        if self.progress_callback is not None:
            self.progress_callback(scenario, skill)

    def run(self, minutes: float, objective_name: str | None = None) -> None:
        """Select and execute objectives until time expires or stop-file appears."""
        chosen = [o for o in self._objectives if o.name == objective_name] if objective_name else self._objectives
        if not chosen: raise ValueError(f"No matching objectives: {objective_name}")
        deadline = self._clock() + minutes * 60
        while self._clock() < deadline and not self._stop_file.exists() and not self.control.stopped:
            data = self._rng.choices(chosen, weights=[max(0.01, o.weight) for o in chosen], k=1)[0]
            self.current_scenario, self.current_skill = data.name, None
            self._context.logger.log({"event": "objective_start", "objective": data.name})
            try:
                self.control.checkpoint()
                YamlObjective(data, self._dependencies).run(self._context, rng=self._rng)
                self._context.logger.log({"event": "objective_end", "objective": data.name})
            except RunStopped:
                self._context.logger.log({"event": "objective_interrupted", "objective": data.name})
                break
            if self._clock() < deadline:
                try:
                    self._pacer.wait("step", self._stop_file.exists)
                except RunStopped:
                    break
        self.current_scenario, self.current_skill = None, None

    def run_once(self, objective_name: str) -> None:
        """Execute one named objective for a quick development dry run."""
        matches = [item for item in self._objectives if item.name == objective_name]
        if not matches: raise ValueError(f"No matching objective: {objective_name}")
        self.current_scenario, self.current_skill = matches[0].name, None
        try:
            YamlObjective(matches[0], self._dependencies).run(self._context, rng=self._rng)
        except RunStopped:
            pass
