"""Persistence and editor validation for UI-authored objectives."""
import pytest
import yaml

from agent.config import ObjectiveData
from agent.objectives.storage import resolve_for_edit, save_as_new, validate_draft


def test_save_as_new_writes_ordered_yaml(tmp_path):
    plan = [
        {"skill": "open_app", "args": {"name": "edge"}},
        {"skill": "search", "args": {"query": "python lists tutorial"}},
        {"skill": "close_app", "args": {}},
    ]
    path = save_as_new(tmp_path, "My Web Search", plan)
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert path.name == "my_web_search.yaml"
    assert saved["name"] == "My Web Search"
    assert [step["skill"] for step in saved["plan"]] == ["open_app", "search", "close_app"]


def test_save_as_new_rejects_duplicate_name(tmp_path):
    plan = [{"skill": "close_app", "args": {}}]
    save_as_new(tmp_path, "My Search", plan)
    with pytest.raises(ValueError, match="already exists"):
        save_as_new(tmp_path, "my search", plan)


@pytest.mark.parametrize("plan, message", [
    ([{"skill": "unknown", "args": {}}], "not available"),
    ([{"skill": "search", "args": {"query": "  "}}], "cannot be empty"),
    ([{"skill": "scroll_and_read", "args": {"bursts": "0"}}], "between 1 and 20"),
])
def test_validate_rejects_invalid_editor_values(plan, message):
    with pytest.raises(ValueError, match=message):
        validate_draft("Valid name", plan)


def test_resolve_for_edit_turns_parameterized_plan_into_draft_values():
    objective = ObjectiveData(
        name="research_topic",
        weight=2,
        params={"queries": ["first search", "second search"]},
        plan=[{"skill": "search", "args": {"query": "{queries}"}}],
    )
    draft = resolve_for_edit(objective)
    assert draft["name"] == "research_topic_custom"
    assert draft["plan"][0]["args"]["query"] == "first search"
    assert draft["params"] == {}
