"""OpenOffice Writer and Calc skills: compose, fill a table, save through the app's own dialog.

The files are written by soffice.bin through its Save As dialog, never by Python, so Sysmon
Event 11 shows the office app as the writer of the file, as it would for a person.

Writer (writing-process research): text is composed in P-bursts of about 8 to 9 words
(Chenoweth and Hayes 2001) separated by pauses of 2 s or more, with longer pauses at paragraph
breaks. Keys inside a burst come from the typing model in compose mode (Conijn 2019 deltas).

Calc (spreadsheet research): Tab across a row and Enter at its end (Calc returns to the row's
first column), a KLM-sized pause before each row and a longer one before a formula, digit keys
timed from 10-key data entry rates, about 1.3% of digits slipped and corrected (Wiseman 2011).
Row labels never start with another label in the same column, because AutoInput would complete
them silently (case-sensitive, Enter accepts). Files are saved as .ods: AOO 4.1.16 cannot write
.xlsx, and .xls raises a "Keep current format" dialog.
"""
from ..behaviour.dist import clamp, ln_median
from ..behaviour.params import P
from ..registry import register_skill
from .base import BaseSkill, SkillContext, SkillError, require_app


def _pick(context: SkillContext, value):
    if isinstance(value, list) and value and isinstance(value[0], (list, dict)):
        return context.rng.choice(value)
    return value


def _bursts(context: SkillContext, words: list[str]) -> list[str]:
    mean, low, high = P("typing.pburst_words")
    out, i = [], 0
    while i < len(words):
        n = int(clamp(round(context.rng.gauss(mean, mean * 0.4)), low, high))
        out.append(" ".join(words[i:i + n])); i += n
    return out


@register_skill("compose_document")
class ComposeDocumentSkill(BaseSkill):
    """Type a title and paragraphs into the editor in front. args: app, document {title, paragraphs}."""
    def execute(self, context: SkillContext, args: dict) -> dict:
        app = args.get("app", "writer")
        require_app(context, app)
        document = args.pop("document", None) or {}
        title = str(document.get("title", args.get("title", "")))
        paragraphs = list(document.get("paragraphs", args.get("paragraphs") or []))
        median, low, high = P("typing.pburst_pause_s")
        context.wait("M")
        words_typed = 0
        if title:
            context.typer.type_text(title, ctx="prose", mode="compose")
            context.typer.press_sequence("enter", "enter")
            context.pacer.sleep(context.rng.uniform(*P("typing.paragraph_pause_s")))
        for index, paragraph in enumerate(paragraphs):
            step_start = context.clock.monotonic()
            for burst in _bursts(context, str(paragraph).split()):
                if context.stop_check(): break
                context.typer.type_text(burst + " ", ctx="prose", mode="compose")
                words_typed += len(burst.split())
                context.pacer.sleep(clamp(ln_median(context.rng, median, 0.5), low, high))
            if index < len(paragraphs) - 1:
                context.typer.press_sequence("backspace", "enter")  # drop the trailing space, new paragraph
            context.log_step("WriteParagraph", {"paragraph": index + 1, "words": len(str(paragraph).split())}, step_start)
            if index < len(paragraphs) - 1:
                context.pacer.sleep(context.rng.uniform(*P("typing.paragraph_pause_s")))
        args.update(title=title, paragraphs=len(paragraphs), words=words_typed, outcome="typed")
        return args


@register_skill("save_document")
class SaveDocumentSkill(BaseSkill):
    """Ctrl+S, wait for Save As, type the filename, Enter, confirm the title changed.

    args: app, filename (string or list; "{n}" becomes a random number so runs never collide).
    """
    def execute(self, context: SkillContext, args: dict) -> str:
        app = args.get("app", "writer")
        require_app(context, app)
        names = args.get("filename", "notes {n}")
        name = str(context.rng.choice(names) if isinstance(names, list) else names)
        name = name.replace("{n}", str(context.rng.randint(10, 99)))  # not behaviour: a unique filename
        args["filename"] = name
        context.wait("M")
        context.typer.combo("ctrl", "s")
        if context.desktop.available:
            if not context.wait_for(lambda: context.perception.is_app("save_dialog", *context.look("save_dialog")[:2]), 10.0):
                raise SkillError("Save As dialog did not appear")
        else:
            context.pacer.sleep(context.rng.uniform(*P("system.dialog_s")))
        context.wait("M")  # deciding on a name
        context.typer.type_text(name, ctx="filename")
        context.pacer.sleep(context.pacer.duration("poll"))
        context.typer.press("enter")
        if not context.desktop.available:
            args["outcome"] = "unverified"
            return "unverified"
        stem = name.lower()
        saved = context.wait_for(lambda: stem in context.desktop.foreground_title().lower(), 10.0)
        args["outcome"] = "saved" if saved else "not_confirmed"
        return args["outcome"]


@register_skill("fill_sheet")
class FillSheetSkill(BaseSkill):
    """Enter a small table into Calc and a SUM row, then bold the header.

    args: table (dict with headers, rows, total_label) or a list of such dicts to pick from.
    """
    def execute(self, context: SkillContext, args: dict) -> dict:
        require_app(context, "calc")
        table = _pick(context, args["table"])
        headers, rows = table["headers"], table["rows"]
        rng, typer = context.rng, context.typer
        row_first, row_median, row_sigma = P("sheet.row_pause")
        hes_p, hes_median = P("sheet.mid_row_hesitation")
        context.wait("M")
        typer.combo("ctrl", "home")
        cells = 0
        for r, row in enumerate([headers] + rows):
            if context.stop_check(): break
            context.pacer.sleep(ln_median(rng, row_first if r == 0 else row_median, row_sigma))
            for c, value in enumerate(row):
                text = str(value)
                typer.type_text(text, ctx="number" if text.replace(".", "").isdigit() else "cell")
                cells += 1
                if c < len(row) - 1:
                    typer.press("tab")
                    if rng.random() < hes_p: context.pacer.sleep(ln_median(rng, hes_median, 0.5))
            typer.press("enter")
        # total row: label, then one SUM per numeric column
        f_median, f_sigma = P("sheet.formula_pause")
        typer.type_text(table.get("total_label", "Total"), ctx="cell")
        last = len(rows) + 1
        for c in range(1, len(headers)):
            typer.press("tab")
            context.pacer.sleep(ln_median(rng, f_median, f_sigma))
            column = chr(ord("A") + c)
            typer.type_text(f"=SUM({column}2:{column}{last})", ctx="cell")
        typer.press("enter")
        # bold the header row: toolbar button when UI Automation sees it, else Ctrl+B
        typer.combo("ctrl", "home")
        context.pacer.sleep(rng.uniform(*P("sheet.after_jump_s")))
        typer.press_sequence(*["shift+right"] * (len(headers) - 1))
        bold = None
        if rng.random() < P("sheet.bold_mouse_p") and context.uia.available:
            bold = context.uia.find(context.desktop.foreground_hwnd(), "button", ("bold",))
        if bold:
            context.mouse.click(*bold.center, bold.width, bold.height)
        else:
            typer.combo("ctrl", "b")
        median, sigma, low, high = P("sheet.check_pause")
        context.pacer.sleep(clamp(ln_median(rng, median, sigma), low, high))  # checking the totals
        args.update(table=table.get("name", "table"), cells=cells, bold="toolbar" if bold else "ctrl_b", outcome="filled")
        return args
