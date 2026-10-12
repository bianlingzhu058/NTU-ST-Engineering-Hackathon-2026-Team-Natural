"""Document entry and save skills for harmless sample content (OpenOffice Writer, or any editor with Ctrl+S)."""
from ..registry import register_skill
from .base import BaseSkill, SkillContext


def _word_bursts(context: SkillContext, text: str) -> list[str]:
    """Split a paragraph into 'P-bursts' the way people compose: chunks of ~8-9 words
    (Gaussian, clipped 2-20), typed then followed by a think-pause. Research: adult
    composing segments run about 9 words (Chenoweth and Hayes 2001)."""
    words, out, i = str(text).split(), [], 0
    rng = context.rng
    while i < len(words):
        n = max(2, min(20, round(rng.gauss(8.5, 3.4)))) if rng else 9
        out.append(" ".join(words[i:i + n])); i += n
    return out or [str(text)]


@register_skill("type_document")
class TypeDocumentSkill(BaseSkill):
    """Compose a title and paragraphs the way a person writes: in short word-bursts with
    a think-pause between bursts and a longer pause at each paragraph break.

    A human does not type a paragraph as one continuous stream — they write a phrase,
    pause to think, write more. Composing in ~8-9 word bursts (Chenoweth and Hayes 2001)
    with 2-10 s inter-burst pauses and 5-15 s at paragraphs gives roughly the measured
    ~19 WPM composing rate and reads unmistakably as writing rather than transcription.

    args: title, paragraphs (list of strings; a list of lists means pick one set at random).
    Keep text ASCII only: input is injected as plain key events.
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        paragraphs = args.get("paragraphs") or [args.get("body", "")]
        if paragraphs and isinstance(paragraphs[0], list):
            paragraphs = context.rng.choice(paragraphs) if context.rng else paragraphs[0]
        context.pacer.wait("settle")  # ensure the just-opened editor window has focus (slower VM)
        # Rest the mouse on the RIGHT side of the page (over the text, not out on the Properties
        # sidebar) and leave it there, the way a person's hand sits near the mouse while typing.
        # 0.46-0.58 keeps it on the page whether or not the sidebar is open; a move only (no
        # click) — telemetry-neutral, just looks human.
        w, h = context.backend.screen_size()
        rng = context.rng
        rest_x = rng.uniform(w * 0.46, w * 0.58) if rng else w * 0.52
        rest_y = rng.uniform(h * 0.35, h * 0.60) if rng else h * 0.48
        context.mouse.move(rest_x, rest_y)
        context.pacer.wait("think")
        total_bursts = 0
        if args.get("title"):
            context.typer.type_text(str(args["title"]))
            context.backend.press("enter"); context.backend.press("enter")
            context.pacer.wait("para")   # settle into the body after the title
        for i, para in enumerate(paragraphs):
            bursts = _word_bursts(context, str(para))
            for j, burst in enumerate(bursts):
                last_burst = j == len(bursts) - 1
                context.typer.type_text(burst if last_burst else burst + " ")
                total_bursts += 1
                if not last_burst:
                    context.pacer.wait("burst")   # think-pause mid-paragraph while composing
            if i < len(paragraphs) - 1:
                context.backend.press("enter"); context.backend.press("enter")
                context.pacer.wait("para")        # longer pause at the paragraph break
        args["paragraphs"] = len(paragraphs); args["bursts"] = total_bursts


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
        context.pacer.wait("read")    # the Save As dialog takes a moment to appear
        context.pacer.wait("settle")  # FIX: let the dialog take focus before typing (slower VM)
        context.typer.type_text(name, exact=True)  # filename must be verbatim (no typos)
        context.pacer.wait("step")
        context.backend.press("enter")  # confirm the filename -> starts the save
        context.pacer.wait("read")
        # FIX (OpenOffice): saving a new .odt pops a "Keep Current Format?" dialog
        # that Word does not. Its default button keeps the current format, so a
        # plain Enter dismisses it. Harmless on apps that show no such dialog
        # (the Enter just lands on the already-saved document).
        context.pacer.wait("settle")
        context.backend.press("enter")
        context.pacer.wait("step")


def _rest_mouse_on_page(context: SkillContext) -> None:
    """Rest the mouse on the right of the page (over the content, clear of any sidebar)."""
    w, h = context.backend.screen_size()
    rng = context.rng
    x = rng.uniform(w * 0.46, w * 0.58) if rng else w * 0.52
    y = rng.uniform(h * 0.35, h * 0.60) if rng else h * 0.48
    context.mouse.move(x, y)


@register_skill("fill_sheet")
class FillSheetSkill(BaseSkill):
    """Enter a small table into Calc, add a SUM row, and bold the header — all by keyboard.

    Mechanics (OpenOffice Calc): Ctrl+Home to A1, Tab across a row and Enter at its end (Calc
    returns to the row's first column), then a Total row with one =SUM() per numeric column, and
    Ctrl+B on the selected header row. Cells are typed EXACT (a slipped digit would be wrong data).

    Gotcha built into the data, not the code: row labels never start with another label in the
    same column, or Calc's AutoInput would silently autocomplete them. Files save as .ods (AOO
    cannot write .xlsx). args: table (dict with headers, rows, total_label) or a list to pick from.
    """
    def execute(self, context: SkillContext, args: dict) -> None:
        table = args.get("table")
        if isinstance(table, list) and table and isinstance(table[0], dict):
            table = context.rng.choice(table) if context.rng else table[0]
        headers, rows = table["headers"], table["rows"]
        total_label = table.get("total_label", "Total")
        context.pacer.wait("settle")      # let the Calc window take focus
        if hasattr(context.backend, "release_modifiers"):
            context.backend.release_modifiers()   # Calc is Tab-heavy; make sure no Win key is stuck
        _rest_mouse_on_page(context)
        context.pacer.wait("think")
        context.backend.hotkey("ctrl", "home")   # jump to cell A1
        context.pacer.wait("step")
        for r, row in enumerate([headers] + rows):
            context.pacer.wait("think" if r == 0 else "burst")   # pause before each row
            for c, value in enumerate(row):
                context.typer.type_text(str(value), exact=True, key_pause="keydata")
                if c < len(row) - 1:
                    context.backend.press("tab")
                context.pacer.wait("cell")       # ONE varied pause per cell: slow + irregular, not metronomic
            context.backend.press("enter")       # Calc wraps to the next row's first column
        # Total row: label, then one SUM per numeric column (data is rows 2..last)
        context.pacer.wait("think")
        context.typer.type_text(total_label, exact=True, key_pause="keydata")
        last = len(rows) + 1
        for c in range(1, len(headers)):
            context.backend.press("tab")
            context.pacer.wait("think")   # pause to think before writing each formula
            col = chr(ord("A") + c)
            context.typer.type_text(f"=SUM({col}2:{col}{last})", exact=True, key_pause="keydata")
            context.pacer.wait("cell")
        context.backend.press("enter")
        # Bold the header row: Ctrl+Home, extend the selection across it, Ctrl+B
        context.pacer.wait("think")
        context.backend.hotkey("ctrl", "home")
        context.pacer.wait("step")
        for _ in range(len(headers) - 1):
            context.backend.hotkey("shift", "right")
        context.backend.hotkey("ctrl", "b")
        context.pacer.wait("read")               # glance over the finished table
        args["table"] = table.get("name", "table"); args["rows"] = len(rows)
