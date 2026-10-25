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


class DeskError(RuntimeError):
    """The desktop is not in the state the bot expects (wrong window in front, no Save As box).
    The task stops and is written down honestly instead of typing into the wrong place."""


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
        self._order = None                   # last real Alt+Tab order read (titles, front first)
        self.mru: list[Window] = [Window("harness", self.HARNESS, "operator window")]
        self.profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        self.switches = 0
        self.saved_files: list[str] = []
        self.eyes = getattr(context, "eyes", None)
        self.sim_folder = "Documents"          # simulator only: which folder the Save As box shows

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

    def _sensing(self) -> bool:
        s = self.ctx.sensor
        return s is not None and getattr(s, "available", False)

    def title(self) -> str:
        return (self.ctx.sensor.foreground_title() or "") if self._sensing() else ""

    def ensure_front(self, win: Window, why: str = "") -> None:
        """Check the right window is in front before typing into it; one Alt+Tab try to fix it,
        else stop the task (never type into the wrong window, VM 25 Oct)."""
        if not self._sensing(): return
        if self.ctx.sensor.foreground_matches(win.needle):
            self._unsnap(win); return
        self.log({"event": "wrong_window", "want": win.needle, "got": self.title(), "why": why})
        real = self._real_place(win)
        if real:                                            # where it really is in the Alt+Tab order
            self._alt_tab(real)
            if self.ctx.sensor.foreground_matches(win.needle):
                if win in self.mru: self._to_front(win)
                self._unsnap(win); return
        for place in range(1, len(self.mru)):               # try each Alt+Tab place once
            self._alt_tab(place)
            if self.ctx.sensor.foreground_matches(win.needle):
                if win in self.mru: self._to_front(win)
                self._unsnap(win); return
        raise DeskError(f"{win.app} not in front")

    def _unsnap(self, win: Window) -> None:
        """A document that is not full screen (and not put in a half on purpose) gets full screen again
        before typing. Writer ended in the top left quarter while the list was typed (VM run 3, 25 Oct,
        finding 13): Win+arrow keys from a Win key the system still saw as held."""
        if win.app not in ("writer", "calc") or win.extra.get("split"): return
        from ..win.uia import front_window
        state = front_window()
        if state is None or state[0]: return
        if hasattr(self.ctx.backend, "release_modifiers"): self.ctx.backend.release_modifiers()
        self.log({"event": "unsnap", "label": win.label, "rect": list(state[1])})
        self._skill("maximize_window", {})

    def _learn_title(self, win: Window, fallback: str) -> None:
        """Take the exact title of a just opened document ('Untitled 2 - OpenOffice Writer')."""
        t = self.title()
        if t and fallback.lower() in t.lower():
            win.needle = t.split(" - ")[0].strip() or fallback

    # mouse helpers for things the eyes found
    def click_el(self, el, double: bool = False) -> None:
        ctx = self.ctx
        x, y = el.center
        ctx.mouse.move(x + ctx.rng.uniform(-0.25, 0.25) * el.width, y + ctx.rng.uniform(-0.2, 0.2) * el.height)
        ctx.pacer.wait("step")
        down, up = getattr(ctx.backend, "mouse_down", None), getattr(ctx.backend, "mouse_up", None)
        for i in range(2 if double else 1):
            if i: ctx.pacer.tiny(ctx.rng.uniform(0.07, 0.16))
            if callable(down) and callable(up):
                down(); ctx.pacer.tiny(ctx.rng.uniform(0.06, 0.12)); up()
            else:
                ctx.backend.click()

    def clipboard_text(self) -> str:
        """What is on the clipboard now (only for lists.copy_check: clipboard). One read right after
        the bot's own Ctrl+C, like glancing at what was copied; never polled."""
        import ctypes, sys
        if not sys.platform.startswith("win"): return ""
        u, k = ctypes.windll.user32, ctypes.windll.kernel32
        u.GetClipboardData.restype = ctypes.c_void_p
        k.GlobalLock.restype = ctypes.c_void_p
        if not u.OpenClipboard(None): return ""
        try:
            h = u.GetClipboardData(13)                 # CF_UNICODETEXT
            if not h: return ""
            p = k.GlobalLock(ctypes.c_void_p(h))
            try:
                return ctypes.wstring_at(p) if p else ""
            finally:
                k.GlobalUnlock(ctypes.c_void_p(h))
        finally:
            u.CloseClipboard()

    def drag_select(self, el) -> None:
        """Select the text of one element with the mouse: press at its left edge, drag to the right."""
        ctx = self.ctx
        y = el.center[1]
        ctx.mouse.move(el.left + 2, y)
        ctx.pacer.wait("step")
        down, up = getattr(ctx.backend, "mouse_down", None), getattr(ctx.backend, "mouse_up", None)
        if callable(down): down()
        steps = ctx.rng.randint(6, 10)
        for i in range(1, steps + 1):
            ctx.backend.move_to(el.left + 2 + (el.width - 3) * i / steps, y + ctx.rng.uniform(-1, 1))
            ctx.pacer.tiny(ctx.rng.uniform(0.015, 0.04))
        ctx.pacer.tiny(ctx.rng.uniform(0.05, 0.15))
        if callable(up): up()
        else: ctx.backend.click()

    # switching
    def focus(self, win: Window, why: str = "") -> None:
        """Alt+Tab to ``win``: hold Alt, Tab once per place in the order, let go."""
        if self.front is win:
            return
        place = self._real_place(win)
        guessed = place is None
        if guessed: place = self.mru.index(win)
        self._alt_tab(place)
        self._to_front(win)
        self.switches += 1
        if self._title_ok(win) is False:
            # off by some places: look at the real order again (each Alt+Tab reorders it), then the guesses
            again = self._real_place(win)
            tries = ([again] if again else []) + list(range(1, len(self.mru)))
            for other in tries:
                self._alt_tab(other)
                if self.ctx.verify_window(win.needle, tries=2, wait_kind="step"):
                    break
            self.log({"event": "switch_recovered", "to": win.label, "order": (self._order or [])[:6]})
        self.log({"event": "switch", "to": win.label, "tabs": place, "why": why})

    def _real_place(self, win: Window):
        """How many Tabs reach ``win``: its place in the order Windows really keeps (front first),
        not the bot's own guess, which went wrong when windows or Edge tabs got in between (#8)."""
        from ..win.uia import alt_tab_titles
        self._order = alt_tab_titles()
        if not self._order: return None
        needle = win.needle.lower().replace("\u200b", "")
        hits = [i for i, t in enumerate(self._order) if needle in t.lower()]
        return hits[0] if hits and hits[0] > 0 else None

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
        if app in ("writer", "calc"): self._learn_title(win, "Untitled")
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
        if self.ctx.verify_window("Untitled", tries=5) is False:
            # Ctrl+N did not give a new document in front: open the app from Start instead
            self.log({"event": "new_document_missing", "app": app, "got": self.title()})
            win = self.open_app(app, label)
            if self.ctx.verify_window("Untitled", tries=4) is False:
                raise DeskError(f"no new {app} document")
            self._learn_title(win, "Untitled")
            return win
        win = Window(app, self.cfg["apps"][app]["title"], label)
        self.mru.insert(0, win)
        self._learn_title(win, "Untitled")
        self.log({"event": "new_document", "app": app, "label": label, "title": win.needle})
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
        """Ctrl+S. The first time this opens Save As: the bot looks at the folder list (eyes), double
        clicks the folder it wants or goes up one level, then types only the file name. It types
        nothing unless the Save As box is really in front."""
        ctx = self.ctx
        if self.front is not win: self.focus(win, "save")
        self.ensure_front(win, "save")
        ctx.pacer.wait("think")
        ctx.backend.hotkey("ctrl", "s")
        if win.file:
            ctx.pacer.wait("step")
            win.dirty = False
            self.log({"event": "save", "file": win.file})
            return win.file
        ext = ".odt" if win.app == "writer" else ".ods"
        # Windows does not allow these in a file name (VM: "Asana for the team?" would fail the save)
        name = "".join(ch for ch in name if ch not in '\\/:*?"<>|').strip(" .") or "notes"
        folder = folder or self.cfg["files"]["work_folder"]
        file, path = self.unique_path(folder, name, ext)
        ctx.pacer.wait("read")
        if ctx.verify_window(["Save As", "Save"], tries=6) is False:
            self.log({"event": "save_box_missing", "got": self.title()})
            raise DeskError("no Save As box")
        ctx.pacer.wait("settle")
        how = self._choose_folder(folder)
        ctx.pacer.wait("step")
        ctx.backend.hotkey("alt", "n")                 # the File name box
        ctx.pacer.tiny(ctx.typer.key_gap())
        ctx.backend.hotkey("ctrl", "a")
        ctx.typer.type_text(file if how != "path" else path, ctx="filename")
        ctx.pacer.wait("step")
        ctx.backend.press("enter")
        ctx.pacer.wait("read")
        # AOO may ask "Keep current format?". Only press Enter if a dialog is really in front.
        title = self.title()
        if title and file.lower() not in title.lower() and ("save" in title.lower() or "format" in title.lower()
                                                          or "openoffice" == title.lower().strip()):
            ctx.backend.press("enter")
            ctx.pacer.wait("step")
        win.file, win.path, win.needle, win.dirty = file, path + ext, file + ext, False
        # Writer renames its window a moment after the save; looking before that read "Untitled 1" and the
        # next step thought the list was not in front (VM run 7, 25 Oct). Wait for the new name.
        ctx.verify_window(win.needle, tries=4, wait_kind="step")
        self.saved_files.append(file)
        if self.eyes is not None and not getattr(self.eyes, "uia", None):
            self.sim_folder = folder.rsplit("\\", 1)[-1]
        self.log({"event": "save_as", "file": file, "folder": folder, "how": how})
        return file

    def _list_items(self) -> list[str]:
        if self.eyes is None or not self.eyes.available: return []
        if not getattr(self.eyes, "uia", None):          # simulator: what this folder would show
            here = self.sim_folder
            self.eyes.dialog_items = (["To do"] + [f for f in self.saved_files if not f.startswith(("todo", "to do"))]
                                      if here == "Documents" else [f for f in self.saved_files if f.startswith(("todo", "to do"))])
        self._items = self.eyes.read(["Save As", "Save"], kinds=("listitem",))
        return [e.name for e in self._items]

    def _choose_folder(self, folder: str) -> str:
        """Get the Save As box into ``folder`` the way a person does. Returns how: 'here', 'opened',
        'up', 'typed' (typed the folder name, Enter) or 'path' (last resort: the full path)."""
        ctx = self.ctx
        want = folder.rsplit("\\", 1)[-1]                 # "To do" or "Documents"
        names = self._list_items()
        # The first Save As of a session fills its file list late; one short retry read it empty and
        # the bot typed the whole path (VM run 3, 25 Oct, finding 11). Wait like a person, look again.
        for _ in range(3):
            if names or self.eyes is None or not self.eyes.available: break
            ctx.pacer.wait("settle"); names = self._list_items()
        if not names:
            # #36: the Calc Save As list read empty on the VM; say what the eyes looked at, to find out why
            from ..win.uia import alt_tab_titles
            self.log({"event": "save_list_empty", "front": self.title(), "windows": (alt_tab_titles() or [])[:6],
                      "items_read": len(getattr(self, "_items", []) or [])})
            if want != "Documents":
                # Save As opens in Documents: typing the folder name + Enter opens it, then the file name
                ctx.backend.hotkey("alt", "n")
                ctx.typer.type_text(want, ctx="filename")
                ctx.backend.press("enter")
                ctx.pacer.wait("settle")
                return "typed"
            return "path"
        looks_todo = any(n.lower().startswith(("todo", "to do ")) for n in names)
        if want == "Documents":
            if "To do" in names or not looks_todo: return "here"
            ctx.backend.hotkey("alt", "up")              # one folder up, back to Documents
            if hasattr(ctx.backend, "release_modifiers"): ctx.backend.release_modifiers()
            if not getattr(self.eyes, "uia", None): self.sim_folder = "Documents"
            ctx.pacer.wait("settle")
            return "up"
        if looks_todo and "To do" not in names: return "here"
        item = next((e for e in self._items if e.name == want), None)
        if item is not None:
            self.click_el(item, double=True)             # open the folder
            if not getattr(self.eyes, "uia", None): self.sim_folder = want
            ctx.pacer.wait("settle")
            return "opened"
        ctx.backend.hotkey("alt", "n")
        ctx.typer.type_text(want, ctx="filename")        # typing a folder name + Enter opens it
        ctx.backend.press("enter")
        ctx.pacer.wait("settle")
        return "typed"

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
            # One Ctrl+W per tab, and more while Edge is still in front: the tab count can be low (a link
            # opened another tab; VM 25 Oct Edge was left open). Stops as soon as Edge is gone, so a
            # further Ctrl+W never lands on a document.
            presses = max(1, win.tabs) + (8 if self._sensing() else 0)
            for _ in range(presses):
                if self._sensing():
                    title = self.title().replace("\u200b", "").lower()
                    if "edge" not in title:
                        break
                    if "close all" in title or "close tabs" in title:
                        ctx.backend.press("enter"); ctx.pacer.wait("step"); continue
                ctx.backend.hotkey("ctrl", "w")
                ctx.pacer.wait("step")
        else:
            ctx.backend.hotkey("alt", "f4")
            ctx.pacer.wait("step")
        self.mru.remove(win)
        self.log({"event": "close", "label": win.label})
