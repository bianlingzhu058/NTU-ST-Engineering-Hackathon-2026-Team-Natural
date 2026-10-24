"""The desktop as the bot keeps it in its head: which windows are open, in which Alt+Tab order.

Apps stay open all day once opened (report). The bot switches with Alt+Tab, pressing Tab as many
times as the window's place in the Alt+Tab order (most recently used first). It keeps that order
itself, because only the bot changes focus, and checks the window title afterwards (title only,
never the screen). If the title is wrong it tries the other places once each.

Apps are opened the way a person does, through the Start menu search, so every app's parent is
explorer.exe. A second Writer or Calc document comes from Ctrl+N inside the open app (no new
process), the way people do it.
"""
from dataclasses import dataclass, field
import os
from ..registry import create_skill


@dataclass
class Window:
    app: str                 # writer, calc, browser, explorer, harness
    needle: str              # piece of the title that identifies it
    label: str = ""
    file: str = ""           # saved file name without extension, "" while untitled
    path: str = ""           # full path once saved
    tabs: int = 0            # browser tabs
    doc: object = None       # WriterDoc / CalcSheet mirror
    dirty: bool = False
    extra: dict = field(default_factory=dict)


class Desk:
    HARNESS = "Synthetic Activity Harness"

    def __init__(self, context, config: dict, log):
        self.ctx, self.cfg, self.log = context, config, log
        self.mru: list[Window] = [Window("harness", self.HARNESS, "operator window")]
        self.profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        self.switches = 0
        self.saved_files: list[str] = []

    # helpers
    def _skill(self, name: str, args: dict) -> dict:
        deps = {"backend": self.ctx.backend, "pacer": self.ctx.pacer, "rng": self.ctx.rng}
        create_skill(name, **deps).run(self.ctx, args)
        return args

    @property
    def front(self) -> Window:
        return self.mru[0]

    def find(self, app: str) -> list[Window]:
        return [w for w in self.mru if w.app == app]

    def _to_front(self, win: Window) -> None:
        self.mru.remove(win); self.mru.insert(0, win)

    def _title_ok(self, win: Window):
        return self.ctx.verify_window(win.needle, tries=3, wait_kind="step")

    # switching
    def focus(self, win: Window, why: str = "") -> None:
        """Alt+Tab to ``win``: hold Alt, Tab once per place in the order, let go."""
        if self.front is win:
            return
        place = self.mru.index(win)
        self._alt_tab(place)
        self._to_front(win)
        self.switches += 1
        if self._title_ok(win) is False:
            for other in range(1, len(self.mru)):          # the order was off: try each place once
                self._alt_tab(other)
                if self.ctx.verify_window(win.needle, tries=2, wait_kind="step"):
                    break
            self.log({"event": "switch_recovered", "to": win.label})
        self.log({"event": "switch", "to": win.label, "tabs": place, "why": why})

    def _alt_tab(self, tabs: int) -> None:
        typer, backend = self.ctx.typer, self.ctx.backend
        self.ctx.pacer.wait("step")
        backend.key_event("alt", True)
        self.ctx.pacer.tiny(typer.key_gap())
        for i in range(tabs):
            if i: self.ctx.pacer.tiny(typer.key_gap() * 1.5)
            typer.press("tab")
        self.ctx.pacer.tiny(typer.key_gap())
        backend.key_event("alt", False)
        self.ctx.pacer.wait("settle")

    # opening
    def open_app(self, app: str, label: str) -> Window:
        spec = self.cfg["apps"][app]
        args = self._skill("open_app", {"name": spec["search"], "strategies": ["start_search"], "expect": spec["title"]})
        win = Window(app, spec["title"], label)
        self.mru.insert(0, win)
        if app == "browser":
            win.tabs = 1
            self._skill("maximize_window", {"first": True})
        self.log({"event": "open_app", "app": app, "label": label, "window_confirmed": args.get("window_confirmed")})
        return win

    def new_document(self, app: str, label: str) -> Window:
        """A new Writer or Calc document: Ctrl+N from an open window of that app, else Start search."""
        same = self.find(app)
        if not same:
            return self.open_app(app, label)
        self.focus(same[0], "new document")
        self.ctx.pacer.wait("think")
        self.ctx.backend.hotkey("ctrl", "n")
        self.ctx.pacer.wait("settle")
        win = Window(app, self.cfg["apps"][app]["title"], label)
        self.mru.insert(0, win)
        self.log({"event": "new_document", "app": app, "label": label})
        return win

    def browser(self, label: str = "browser") -> Window:
        wins = self.find("browser")
        if wins:
            self.focus(wins[0], label)
            return wins[0]
        return self.open_app("browser", label)

    def explorer(self) -> Window:
        wins = self.find("explorer")
        if wins:
            self.focus(wins[0], "files")
            return wins[0]
        self._skill("open_explorer", {})
        win = Window("explorer", "File Explorer", "File Explorer")
        self.mru.insert(0, win)
        return win

    # saving
    def unique_path(self, folder: str, name: str, ext: str) -> tuple[str, str]:
        """Pick a file name not used yet (a second run on the same day gets 'name 2')."""
        base = os.path.join(self.profile, folder)
        candidate, n = name, 2
        while os.path.exists(os.path.join(base, candidate + ext)) or candidate in self.saved_files:
            candidate, n = f"{name} {n}", n + 1
        return candidate, os.path.join(base, candidate)

    def save(self, win: Window, folder: str = "", name: str = "") -> str:
        """Ctrl+S. The first time this opens Save As: type the full path, Enter."""
        ctx = self.ctx
        if self.front is not win: self.focus(win, "save")
        ctx.pacer.wait("think")
        ctx.backend.hotkey("ctrl", "s")
        if win.file:
            ctx.pacer.wait("step")
            win.dirty = False
            self.log({"event": "save", "file": win.file})
            return win.file
        ext = ".odt" if win.app == "writer" else ".ods"
        file, path = self.unique_path(folder or self.cfg["files"]["work_folder"], name, ext)
        ctx.pacer.wait("read")
        ctx.verify_window(["Save As", "Save"], tries=4)
        ctx.pacer.wait("settle")
        ctx.typer.type_text(path, ctx="filename")
        ctx.pacer.wait("step")
        ctx.backend.press("enter")
        ctx.pacer.wait("read")
        # AOO may ask "Keep current format?". Only press Enter if a dialog is really in front:
        # an Enter into the document would add an empty line.
        title = ctx.sensor.foreground_title() if ctx.sensor is not None and getattr(ctx.sensor, "available", False) else None
        if title is not None and file.lower() not in title.lower() and win.needle.lower() not in title.lower():
            ctx.backend.press("enter")
            ctx.pacer.wait("step")
        win.file, win.path, win.needle, win.dirty = file, path + ext, file, False
        self.saved_files.append(file)
        self.log({"event": "save_as", "file": file, "folder": folder})
        return file

    # closing
    def close(self, win: Window) -> None:
        ctx = self.ctx
        if win.app == "harness": return
        self.focus(win, "close")
        if ctx.sensor is not None and getattr(ctx.sensor, "available", False) and ctx.sensor.foreground_matches([self.HARNESS]):
            self.log({"event": "close_skipped_on_harness", "label": win.label})
            self.mru.remove(win)
            return
        ctx.pacer.wait("think")
        if win.app == "browser":
            for _ in range(max(1, win.tabs)):
                ctx.backend.hotkey("ctrl", "w")
                ctx.pacer.wait("step")
        else:
            ctx.backend.hotkey("alt", "f4")
            ctx.pacer.wait("step")
        self.mru.remove(win)
        self.log({"event": "close", "label": win.label})
