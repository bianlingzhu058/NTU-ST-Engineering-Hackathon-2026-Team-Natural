"""Registries and decorators for extending skills and objectives."""
from typing import Any, TypeVar

from .interfaces import Skill

S = TypeVar("S", bound=type[Skill])
SKILLS: dict[str, type[Skill]] = {}


def register_skill(name: str):
    """Register a skill class by its YAML-facing name."""
    def decorate(cls: S) -> S:
        if name in SKILLS:
            raise ValueError(f"Duplicate skill: {name}")
        SKILLS[name] = cls
        return cls
    return decorate


def create_skill(name: str, **dependencies: Any) -> Skill:
    """Create a registered skill with injected dependencies."""
    try:
        return SKILLS[name](**dependencies)
    except KeyError as exc:
        raise ValueError(f"Unknown skill: {name}") from exc
