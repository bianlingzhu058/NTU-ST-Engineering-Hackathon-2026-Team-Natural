"""A simulated Windows desktop driven by the agent's own key and mouse events.

Offline runs are only worth something if the agent's checks can fail. So instead of a recorder
that lets every step "succeed", this state machine answers window-title, process, rectangle and
UI Automation queries from what the agent actually pressed and clicked:

  Win+1 / Win, type, Enter   Chrome or an OpenOffice module opens after a few polls; sometimes
                             OpenOffice shows its Start Center instead (as it can on the VM)
  Chrome                     Ctrl+L, host, Enter loads a page through a loading title; new hosts
                             show "Privacy error" whose Advanced button reveals a Proceed link
                             (typing thisisunsafe also works); pages expose links with screen
                             rectangles; some links lead to dead hosts; Ctrl+click opens a
                             background tab; Ctrl+Tab, Alt+Left/Right, F5, Ctrl+F, Ctrl+W, Alt+F4
  Writer / Calc              Ctrl+S opens "Save As", the typed name and Enter save, Alt+F4 closes

Pessimistic on purpose: every new host hits the certificate warning, and a quarter of links are
dead, so the recovery paths run in every simulated session.
"""
import random
from ..win.uia import Element

CHROME = " - Google Chrome"
SCREEN = (1920, 1080)
WINDOW = (0, 0, 1920, 1032)
LINK_WORDS = ["Shop", "Support", "Products", "Pricing", "Deals", "News", "Learn more", "Compare models",
              "Accessories", "Business", "Shipping", "Contact", "Specs", "Reviews", "Latest", "Markets"]


class FakeDesktop:
    """Keystroke- and click-driven simulation of Windows, Chrome and OpenOffice."""
    available = True

    def __init__(self, rng: random.Random | None = None, startup_polls: int = 3, dead_link_rate: float = 0.25,
                 start_center_rate: float = 0.2, clock=None):
        self._rng, self._startup, self._dead, self._start_center = rng or random.Random(), startup_polls, dead_link_rate, start_center_rate
        self._clock = clock
        self.app, self._pending, self._pending_app = "desktop", 0, None
        self._held: set[str] = set()
        self._win_alone = False
        self._start_buffer: str | None = None
        self._pos = (SCREEN[0] // 2, SCREEN[1] // 2)
        self._tabs: list[dict] = []
        self._tab = 0
        self._address: str | None = None
        self._find: str | None = None
        self._find_term = ""
        self._bypass = ""
        self._proceeded: set[str] = set()
        self._office: dict = {}
        self._save_buffer: str | None = None
        self._memory = 14.0
        self.loading_polls = 0
        self.events: list[str] = []

    # desktop interface used by the agent
    def _tick(self) -> None:
        if self._pending:
            self._pending -= 1
            if not self._pending: self._finish_launch()
        if self.loading_polls: self.loading_polls -= 1

    def foreground_title(self) -> str:
        self._tick()
        if self._pending: return "Search" if self._start_buffer is not None else "Program Manager"
        if self.app == "chrome":
            page = self._page()
            if self.loading_polls: return page["host"] + CHROME
            return page["title"] + CHROME
        if self.app in ("writer", "calc"):
            name = self._office.get("name") or "Untitled 1"
            return f"{name} - OpenOffice {'Writer' if self.app == 'writer' else 'Calc'}"
        if self.app == "save": return "Save As"
        if self.app == "start_center": return "OpenOffice"
        if self._start_buffer is not None: return "Search"
        return "Program Manager"

    def foreground_process(self) -> str:
        return {"chrome": "chrome.exe", "writer": "soffice.bin", "calc": "soffice.bin", "save": "soffice.bin",
                "start_center": "soffice.bin"}.get(self.app, "explorer.exe")

    def foreground_hwnd(self) -> int: return 0x1000 + len(self.app)
    def foreground_rect(self): return WINDOW if self.app != "desktop" else None

    def metrics(self) -> dict[str, float]:
        elapsed = self._clock.monotonic() if self._clock is not None else 0.0
        self._memory = min(28.0, max(13.0, self._memory + self._rng.gauss(0.03, 0.2)))
        return {"cpu_seconds": round(0.4 + 0.003 * elapsed, 3), "working_set_mb": round(self._memory, 2),
                "private_bytes_mb": round(self._memory - 4.0, 2)}

    # UI Automation stand-in
    available_uia = True

    def elements(self, hwnd, kind="hyperlink", visible_only=True) -> list[Element]:
        if self.app == "start_center" and kind == "button":
            return [Element("Text Document", 300, 300, 420, 340, "button"), Element("Spreadsheet", 300, 360, 420, 400, "button")]
        if self.app == "calc" and kind == "button":
            return [Element("Bold", 600, 70, 624, 94, "button")]
        if self.app != "chrome" or self.loading_polls: return []
        page = self._page()
        if page["state"] == "interstitial":
            if kind == "button": return [Element("Advanced", 700, 640, 820, 680, "button")]
            if kind == "hyperlink" and page.get("expanded"):
                return [Element(f"Proceed to {page['host']} (unsafe)", 700, 820, 960, 845)]
            return []
        if kind != "hyperlink" or page["state"] != "ok": return []
        return [link["element"] for link in page["links"] if link["element"].top < WINDOW[3] - 60]

    def find(self, hwnd, kind, words):
        for item in self.elements(hwnd, kind):
            if any(w in item.name.lower() for w in words): return item
        return None

    # helpers
    def _page(self) -> dict:
        return self._tabs[self._tab]["pages"][self._tabs[self._tab]["index"]]

    def _new_page(self, host: str, title: str | None = None, dead: bool = False) -> dict:
        if dead: return {"host": host, "title": host, "state": "dead", "links": []}
        if host not in self._proceeded and not host.startswith("new"):
            return {"host": host, "title": "Privacy error", "state": "interstitial", "links": [], "target": title or host}
        links = []
        for i in range(self._rng.randint(8, 20)):
            word = self._rng.choice(LINK_WORDS)
            x, y = self._rng.randint(40, 1700), self._rng.randint(150, 1400)
            links.append({"element": Element(word, x, y, x + 12 * len(word), y + 22),
                          "dead": self._rng.random() < self._dead, "word": word})
        return {"host": host, "title": (title or host.split(".")[-2].capitalize()), "state": "ok", "links": links}

    def _go(self, page: dict, new_entry: bool = True) -> None:
        tab = self._tabs[self._tab]
        if new_entry:
            del tab["pages"][tab["index"] + 1:]
            tab["pages"].append(page); tab["index"] = len(tab["pages"]) - 1
        else:
            tab["pages"][tab["index"]] = page
        self.loading_polls = self._rng.randint(1, 3)

    def _launch(self, app: str) -> None:
        self._pending_app, self._pending = app, self._startup

    def _finish_launch(self) -> None:
        app = self._pending_app
        if app in ("writer", "calc") and self._rng.random() < self._start_center:
            self.app, self._office = "start_center", {"want": app}
        elif app == "chrome":
            self.app = "chrome"
            if not self._tabs:
                self._tabs, self._tab = [{"pages": [{"host": "newtab", "title": "New Tab", "state": "ok", "links": []}], "index": 0}], 0
        else:
            self.app, self._office = app, {"module": app}
        self._start_buffer = None
        self.events.append(f"opened {self.app}")

    def _hit(self, kind_filter=None):
        x, y = self._pos
        for kind in ("button", "hyperlink"):
            for item in self.elements(0, kind):
                if item.left - 6 <= x <= item.right + 6 and item.top - 6 <= y <= item.bottom + 6:
                    return item
        return None

    # input observer
    def observe(self, name: str, payload) -> None:
        if name == "move_to": self._pos = payload; return
        if name == "key_down": return self._key_down(str(payload).lower())
        if name == "key_up":
            key = str(payload).lower()
            if key == "win" and self._win_alone: self._start_buffer, self._win_alone = "", False
            self._held.discard(key); return
        if name == "char_down": return self._char(str(payload))
        if name == "button_up": return self._click()

    def _key_down(self, key: str) -> None:
        held = self._held
        if key in ("ctrl", "alt", "shift", "win"):
            held.add(key); self._win_alone = key == "win"; return
        self._win_alone = False
        if "win" in held and key.isdigit():
            if key == "1": self._launch("chrome")
            return
        if self._start_buffer is not None:
            if key == "enter":
                text, self._start_buffer = self._start_buffer.lower(), None
                if "chrome" in text: self._launch("chrome")
                elif "writer" in text: self._launch("writer")
                elif "calc" in text: self._launch("calc")
                elif "openoffice" in text: self._launch("writer")
            elif key == "escape": self._start_buffer = None
            elif key == "backspace": self._start_buffer = self._start_buffer[:-1]
            return
        if "alt" in held and key == "f4": return self._close_app()
        if self.app == "chrome": return self._chrome_key(key)
        if self.app in ("writer", "calc"):
            if "ctrl" in held and key == "s": self.app, self._save_buffer = "save", ""
            return
        if self.app == "save":
            if key == "enter":
                name = (self._save_buffer or "file").strip()
                self.app = self._office.get("module", "writer")
                self._office["name"] = name + (".odt" if self.app == "writer" else ".ods")
            return

    def _char(self, char: str) -> None:
        if self._start_buffer is not None:
            self._start_buffer += char; return
        if self.app == "save": self._save_buffer = (self._save_buffer or "") + char; return
        if self.app != "chrome": return
        if self._address is not None: self._address += char; return
        if self._find is not None: self._find += char; return
        page = self._page()
        if page["state"] == "interstitial":
            self._bypass = (self._bypass + char)[-12:]
            if self._bypass == "thisisunsafe": self._proceed()

    def _backspace(self) -> None:
        if self._address is not None: self._address = self._address[:-1]
        elif self._find is not None: self._find = self._find[:-1]

    def _chrome_key(self, key: str) -> None:
        held = self._held
        if key == "backspace": return self._backspace()
        if "ctrl" in held:
            if key == "l": self._address, self._find = "", None
            elif key == "f": self._find, self._address = "", None
            elif key == "w": self._close_tab()
            elif key == "tab" and len(self._tabs) > 1: self._tab = (self._tab + 1) % len(self._tabs)
            return
        if "alt" in held:
            tab = self._tabs[self._tab]
            if key == "left" and tab["index"] > 0: tab["index"] -= 1; self.loading_polls = 1
            elif key == "right" and tab["index"] < len(tab["pages"]) - 1: tab["index"] += 1; self.loading_polls = 1
            return
        if key == "escape":
            if self._find is not None: self._find_term, self._find = self._find, None
            self._address = None
        elif key == "enter":
            if self._address is not None:
                text, self._address = self._address.strip().lower(), None
                host = self._complete(text)
                self._go(self._new_page(host))
            elif self._find_term:
                term, self._find_term = self._find_term.lower(), ""
                for link in self._page().get("links", []):
                    if term in link["word"].lower():
                        self._follow(link); break
        elif key == "f5":
            self.loading_polls = self._rng.randint(1, 2)

    def _complete(self, typed: str) -> str:
        for tab in self._tabs:
            for page in tab["pages"]:
                if page["host"].startswith(typed) and page["host"] != "newtab": return page["host"]
        return typed

    def _proceed(self) -> None:
        page = self._page()
        self._proceeded.add(page["host"]); self._bypass = ""
        self._go(self._new_page(page["host"], page.get("target")), new_entry=False)

    def _follow(self, link: dict, background: bool = False) -> None:
        host = self._page()["host"]
        target = self._new_page(f"{link['word'].lower().replace(' ', '')}.{host}", dead=True) if link["dead"] \
            else self._new_page(host, f"{link['word']} - {host.split('.')[-2].capitalize()}")
        if background:
            self._tabs.append({"pages": [target], "index": 0})
        else:
            self._go(target)

    def _click(self) -> None:
        item = self._hit()
        if item is None:
            self._bypass = ""
            return
        if self.app == "start_center":
            self.app = "writer" if item.name == "Text Document" else "calc"
            self._office = {"module": self.app}
            return
        if self.app != "chrome": return
        page = self._page()
        if item.name == "Advanced": page["expanded"] = True; return
        if item.name.startswith("Proceed"): return self._proceed()
        for link in page.get("links", []):
            if link["element"] == item:
                self._follow(link, background="ctrl" in self._held)
                return

    def _close_tab(self) -> None:
        del self._tabs[self._tab]
        if not self._tabs: self.app = "desktop"; return
        self._tab = min(self._tab, len(self._tabs) - 1)

    def _close_app(self) -> None:
        if self.app == "chrome": self._tabs, self._tab = [], 0
        self.app, self._office = "desktop", {}
        self.events.append("closed")
