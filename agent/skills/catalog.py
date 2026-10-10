"""Editor-facing descriptions for the browsing and launch skills."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SkillField:
    name: str
    label: str
    default: str
    required: bool = True
    kind: str = "text"


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    label: str
    description: str
    fields: tuple[SkillField, ...] = ()


SKILL_CATALOG = (
    SkillDefinition("open_app", "Open browser", "Open the selected application from the Windows Start menu.",
                    (SkillField("name", "Application name", "edge"),)),
    SkillDefinition("go_to_url", "Go to URL", "Navigate to a URL in the foreground browser.",
                    (SkillField("url", "URL", "https://example.com"),)),
    SkillDefinition("search", "Search the web", "Search from the browser address bar.",
                    (SkillField("query", "Search query", "Python lists tutorial"),)),
    SkillDefinition("scroll_and_read", "Scroll and read", "Scroll through the current page.",
                    (SkillField("bursts", "Scroll bursts (1–20)", "3", kind="integer"),)),
    SkillDefinition("find_on_page", "Find on page", "Use the browser's find feature.",
                    (SkillField("text", "Text to find", ""),)),
    SkillDefinition("close_app", "Close browser", "Close the foreground application.", ()),
)

SKILL_DEFINITIONS = {definition.name: definition for definition in SKILL_CATALOG}
