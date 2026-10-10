"""Execution adapter for ordered YAML objective plans."""
from dataclasses import dataclass
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
    def _expand(self, value: Any, params: dict[str, Any]) -> Any:
        if isinstance(value, dict): return {k: self._expand(v, params) for k, v in value.items()}
        if isinstance(value, list): return [self._expand(v, params) for v in value]
        if isinstance(value, str): return re.sub(r"\{([\w_]+)\}", lambda m: str(params.get(m.group(1), m.group(0))), value)
        return value
    def run(self, context: Any, *, rng=None) -> None:
        """Execute plan calls, cycling query parameters when requested."""
        queries = self.data.params.get("queries", [])
        for index, step in enumerate(self.data.plan):
            args = self._expand(step.get("args", {}), self.data.params)
            if "{query}" in str(step.get("args", {})) and queries:
                args["query"] = (rng or __import__("random")).choice(queries)
            skill = create_skill(step["skill"], **self.skill_dependencies)
            context.report_progress(self.data.name, step["skill"])
            skill.run(context, args)
