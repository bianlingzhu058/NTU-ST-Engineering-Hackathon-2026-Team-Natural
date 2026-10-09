"""Document entry and save skills for harmless test content."""
from ..registry import register_skill
from .base import BaseSkill, SkillContext


@register_skill("type_document")
class TypeDocumentSkill(BaseSkill):
    """Enter a title and body into the active document editor."""
    def execute(self, context: SkillContext, args: dict) -> None:
        context.typer.type_text(str(args.get("title", "")))
        context.backend.press("enter")
        context.typer.type_text(str(args.get("body", "")))


@register_skill("save_file")
class SaveFileSkill(BaseSkill):
    """Save the active document through the application's Save As UI."""
    def execute(self, context: SkillContext, args: dict) -> None:
        context.backend.hotkey("ctrl", "shift", "s")
        context.pacer.wait("step")
        context.typer.type_text(str(args["path"]))
        context.backend.press("enter")
        context.pacer.wait("step")
