"""Browser navigation stubs composed from input primitives."""
from ..registry import register_skill
from .base import BaseSkill, SkillContext


@register_skill("go_to_url")
class GoToUrlSkill(BaseSkill):
    """Navigate the foreground browser to a supplied URL."""
    def execute(self, context: SkillContext, args: dict) -> None:
        context.action("hotkey", "ctrl", "l")
        context.typer.type_text(str(args["url"]))
        context.action("press", "enter")
        context.pacer.wait("read")


@register_skill("search")
class SearchSkill(BaseSkill):
    """Search from the browser address bar with a supplied query."""
    def execute(self, context: SkillContext, args: dict) -> None:
        context.action("hotkey", "ctrl", "l")
        context.typer.type_text(str(args["query"]))
        context.action("press", "enter")
        context.pacer.wait("read")


@register_skill("scroll_and_read")
class ScrollAndReadSkill(BaseSkill):
    """Scroll the foreground page using bounded bursts."""
    def execute(self, context: SkillContext, args: dict) -> None: context.scroller.scroll_bursts(int(args.get("bursts", 3)))


@register_skill("find_on_page")
class FindOnPageSkill(BaseSkill):
    """Use browser find to locate a supplied phrase."""
    def execute(self, context: SkillContext, args: dict) -> None:
        context.action("hotkey", "ctrl", "f")
        context.typer.type_text(str(args["text"]))
        context.action("press", "enter")
        context.action("press", "escape")
