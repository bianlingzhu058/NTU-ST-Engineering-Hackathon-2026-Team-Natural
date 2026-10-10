"""Registries and decorators for extending skills and objectives."""
from inspect import Parameter, signature
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
        skill_type = SKILLS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown skill: {name}") from exc
    parameters = signature(skill_type).parameters.values()
    accepts_extra = any(parameter.kind is Parameter.VAR_KEYWORD for parameter in parameters)
    if accepts_extra:
        return skill_type(**dependencies)
    accepted = {parameter.name for parameter in parameters
                if parameter.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY)}
    return skill_type(**{key: value for key, value in dependencies.items() if key in accepted})
