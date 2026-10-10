"""Persistence and validation helpers for objectives authored in the UI."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ..config import ObjectiveData, load_objectives
from ..skills.catalog import SKILL_DEFINITIONS


def _first_param(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else value


def resolve_for_edit(objective: ObjectiveData) -> dict[str, Any]:
    """Make an editable copy with objective placeholders replaced by defaults."""
    def expand(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: expand(item) for key, item in value.items()}
        if isinstance(value, list):
            return [expand(item) for item in value]
        if isinstance(value, str):
            def replace(match):
                key = match.group(1)
                fallback = objective.params.get("queries", match.group(0)) if key == "query" else match.group(0)
                param = _first_param(objective.params.get(key, fallback))
                return str(param)
            return re.sub(r"\{([\w_]+)\}", replace, value)
        return value

    return {"name": f"{objective.name}_custom", "weight": objective.weight,
            "params": {}, "plan": expand(objective.plan)}


def validate_draft(name: str, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate editor data and normalize field values for YAML persistence."""
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Enter a name for this objective.")
    if len(clean_name) > 80:
        raise ValueError("Objective names must be 80 characters or fewer.")
    if any(ord(character) < 32 for character in clean_name):
        raise ValueError("Objective names cannot contain control characters.")
    if not isinstance(plan, list):
        raise ValueError("The skill plan must be a list.")
    if not plan:
        raise ValueError("Add at least one skill before saving.")
    if len(plan) > 100:
        raise ValueError("Objectives can contain at most 100 skills.")

    normalized: list[dict[str, Any]] = []
    for index, step in enumerate(plan, start=1):
        if not isinstance(step, dict):
            raise ValueError(f"Skill {index} must be a valid plan entry.")
        skill_name = step.get("skill")
        definition = SKILL_DEFINITIONS.get(skill_name)
        if definition is None:
            raise ValueError(f"Skill {index} is not available in the objective editor.")
        args = step.get("args", {})
        if not isinstance(args, dict):
            raise ValueError(f"Arguments for {definition.label} must be a mapping.")
        clean_args: dict[str, Any] = {}
        for field in definition.fields:
            raw = args.get(field.name, field.default)
            if field.kind == "integer":
                try:
                    value = int(raw)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"{field.label} for {definition.label} must be a whole number.") from exc
                if not 1 <= value <= 20:
                    raise ValueError(f"{field.label} for {definition.label} must be between 1 and 20.")
            else:
                value = str(raw).strip()
                if field.required and not value:
                    raise ValueError(f"{field.label} for {definition.label} cannot be empty.")
            if value != "" or field.required:
                clean_args[field.name] = value
        normalized.append({"skill": skill_name, "args": clean_args})
    return normalized


def save_as_new(directory: Path, name: str, plan: list[dict[str, Any]], weight: float = 1) -> Path:
    """Save a validated objective under a new, non-conflicting YAML filename."""
    clean_name = name.strip()
    normalized = validate_draft(clean_name, plan)
    existing = load_objectives(directory) if directory.exists() else []
    if any(item.name.casefold() == clean_name.casefold() for item in existing):
        raise ValueError("An objective with that name already exists. Choose a new name.")
    slug = re.sub(r"[^a-z0-9]+", "_", clean_name.casefold()).strip("_") or "objective"
    path = directory / f"{slug}.yaml"
    if path.exists():
        raise ValueError("An objective file with that name already exists. Choose a different name.")
    payload = {"name": clean_name, "weight": float(weight), "params": {}, "plan": normalized}
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path
