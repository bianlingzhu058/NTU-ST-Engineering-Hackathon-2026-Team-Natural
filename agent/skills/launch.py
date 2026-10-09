"""GUI-only application open and close skills."""
from ..registry import register_skill
from .base import BaseSkill, SkillContext


@register_skill("open_app")
class OpenAppSkill(BaseSkill):
    """Open an application through the Windows Start menu UI."""
    def execute(self, context: SkillContext, args: dict) -> None:
        context.backend.press("win")
        context.pacer.wait("step")
        context.typer.type_text(str(args["name"]))
        context.pacer.wait("step")
        context.backend.press("enter")
        context.pacer.wait("read")


@register_skill("close_app")
class CloseAppSkill(BaseSkill):
    """Close the foreground application using its normal UI shortcut."""
    def execute(self, context: SkillContext, args: dict) -> None:
        context.backend.hotkey("alt", "f4")
