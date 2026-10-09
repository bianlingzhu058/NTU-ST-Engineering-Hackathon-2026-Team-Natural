"""Typed configuration values and YAML loading."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml


@dataclass(frozen=True)
class AgentConfig:
    """Stores validated timing, interaction, runner, and logging settings."""
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "AgentConfig":
        """Load settings from a YAML file."""
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(data)

    def section(self, name: str) -> dict[str, Any]:
        """Return a named settings section."""
        return dict(self.raw.get(name, {}))


@dataclass(frozen=True)
class ObjectiveData:
    """Holds one named objective and its ordered skill plan."""
    name: str
    weight: float
    params: dict[str, Any]
    plan: list[dict[str, Any]]

    @classmethod
    def load(cls, path: Path) -> "ObjectiveData":
        """Parse and minimally validate one objective file."""
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not raw.get("name") or not isinstance(raw.get("plan"), list):
            raise ValueError(f"Invalid objective file: {path}")
        return cls(raw["name"], float(raw.get("weight", 1)), raw.get("params", {}), raw["plan"])


def load_objectives(directory: Path) -> list[ObjectiveData]:
    """Load objective YAML files from a directory."""
    return [ObjectiveData.load(path) for path in sorted(directory.glob("*.yaml"))]
