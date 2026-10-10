"""Document entry and save skills for harmless sample content (Word, or any editor with Ctrl+S)."""
from ..registry import register_skill
from .base import BaseSkill, SkillContext


@register_skill("type_document")
class TypeDocumentSkill(BaseSkill):
    """Type a title and one or more paragraphs with thinking pauses between them.

    args: title, paragraphs (list of strings; a list of lists means pick one set at random).
    Keep text ASCII only: input is injected as plain key events.
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        paragraphs = args.get("paragraphs") or [args.get("body", "")]
        if paragraphs and isinstance(paragraphs[0], list):
            paragraphs = context.rng.choice(paragraphs) if context.rng else paragraphs[0]
        context.pacer.wait("settle")  # FIX: ensure the just-opened editor window has focus (slower VM)
        context.pacer.wait("think")
        if args.get("title"):
            context.typer.type_text(str(args["title"]))
            context.backend.press("enter"); context.backend.press("enter")
            context.pacer.wait("think")
        for i, para in enumerate(paragraphs):
            context.typer.type_text(str(para))
            if i < len(paragraphs) - 1:
                context.backend.press("enter"); context.backend.press("enter")
                context.pacer.wait("think")
        args["paragraphs"] = len(paragraphs)


@register_skill("save_file")
class SaveFileSkill(BaseSkill):
    """Save the document with Ctrl+S, typing a filename into the save dialog's focused name box.

    args: filename (string or list; "{n}" is replaced by a random number so repeated runs never collide).
    Works for Word's simplified save pane, WordPad and Notepad (Ctrl+S on a new document).
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        names = args.get("filename", "notes {n}")
        name = str(context.rng.choice(names) if isinstance(names, list) and context.rng else (names[0] if isinstance(names, list) else names))
        name = name.replace("{n}", str(context.rng.randint(100, 9999)) if context.rng else "1")
        args["filename"] = name
        context.pacer.wait("think")
        context.backend.hotkey("ctrl", "s")
        context.pacer.wait("read")    # the save pane takes a moment to appear
        context.pacer.wait("settle")  # FIX: let the dialog take focus before typing (slower VM)
        context.typer.type_text(name)
        context.pacer.wait("step")
        context.backend.press("enter")
        context.pacer.wait("read")
