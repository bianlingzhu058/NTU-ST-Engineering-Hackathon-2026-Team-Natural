"""A small simulated Windows desktop, driven by the keystrokes the agent sends.

This is what makes an offline dry run worth anything. A fake backend that only records calls
lets the agent walk straight past every check: the browser "opens" even when nothing opened,
navigation always "works", and the interstitial and dead-page branches are never executed. So
instead the fake desktop answers title and process queries from a state machine that reacts to
the real key events:

  Win+1 / Start search      a browser window appears, after a couple of polls (startup latency)
  Ctrl+L, text, Enter       navigation, which lands on the page, the TLS interstitial, or a
                            dead host, with configurable probabilities
  thisisunsafe / Tab+Enter  the two interstitial bypasses, the first always works
  Ctrl+T / Ctrl+W / Alt+Left  tab open, tab close, history back
  F5                        reload, with the navigation dice rolled again

It is deliberately pessimistic by default (half the navigations hit the expired-certificate
interstitial, like the organisers' mock sites do today), so a dry run proves the recovery paths.
"""
import random


class FakeDesktop:
    """Answers desktop queries from a keystroke-driven state machine."""
    available = True

    def __init__(self, rng: random.Random | None = None, privacy_error_rate: float = 0.5,
                 unreachable_rate: float = 0.12, startup_polls: int = 2, clock=None, link_hit_rate: float = 0.7):
        self._rng = rng or random.Random()
        self._privacy, self._unreachable, self._startup_polls = privacy_error_rate, unreachable_rate, startup_polls
        self._clock, self._link_hit_rate = clock, link_hit_rate
        self.title, self.process = "Program Manager", "explorer.exe"
        self._pending, self._address_bar, self._buffer = 0, False, ""
        self._tabs, self._history, self._interstitial_tabs, self._tabbed = 0, [], 0, 0
        self._host, self._memory, self._opening = "", 13.0, "browser"
        self._slots = {1: "browser", 2: "word"}  # matches the pinned taskbar order the runbook sets up

    # desktop interface
    def foreground_title(self) -> str:
        if self._pending:
            self._pending -= 1
            if not self._pending: self._open_browser() if self._opening == "browser" else self._open_word()
            else: return "Program Manager"
        return self.title

    def foreground_process(self) -> str:
        self.foreground_title()  # same startup latency applies to the process query
        return self.process

    def metrics(self) -> dict[str, float]:
        """Plausible counters for a sleeping interpreter: CPU creeps, memory walks in a band."""
        elapsed = self._clock.monotonic() if self._clock is not None else 0.0
        self._memory = min(26.0, max(12.5, self._memory + self._rng.gauss(0.04, 0.25)))
        return {"cpu_seconds": round(0.35 + 0.004 * elapsed, 3), "working_set_mb": round(self._memory, 2),
                "private_bytes_mb": round(self._memory - 4.3, 2)}

    # state transitions
    def _open_browser(self) -> None:
        self.title, self.process, self._tabs = "New tab - Microsoft​ Edge", "msedge.exe", 1

    def _open_word(self) -> None:
        self.title, self.process = "Document1 - Word", "winword.exe"

    def _show(self, page: str) -> None:
        suffix = "Word" if self.process == "winword.exe" else "Microsoft​ Edge"
        self.title = f"{page} - {suffix}"

    def _navigate(self, target: str) -> None:
        host = target.replace("https://", "").replace("http://", "").strip("/ ") or "new tab"
        self._history.append(self.title)
        self._host, self._tabbed = host, 0
        roll = self._rng.random()
        if roll < self._privacy:
            self._interstitial_tabs, self._pending_host = 1, host
            self._show("Privacy error")
        elif roll < self._privacy + self._unreachable:
            self._interstitial_tabs = 0
            self._show(f"{host} can't be reached")
        else:
            self._interstitial_tabs = 0
            self._show(host.split("/")[0])

    def observe(self, name: str, payload) -> None:
        """React to one input call from the agent."""
        if name == "hotkey":
            keys = tuple(k.lower() for k in payload)
            if keys[:1] == ("win",) and len(keys) == 2 and keys[1].isdigit():
                self._launch(self._slots.get(int(keys[1]), "browser"))
            elif keys == ("win", "r"): self._address_bar, self._buffer = True, ""
            elif keys == ("ctrl", "l") and self.process == "msedge.exe": self._address_bar, self._buffer = True, ""
            elif keys == ("ctrl", "t") and self.process == "msedge.exe":
                self._tabs += 1; self._interstitial_tabs = 0; self._show("New tab")
            elif keys == ("ctrl", "w") and self.process == "msedge.exe":
                self._tabs -= 1
                if self._tabs <= 0: self.title, self.process = "Program Manager", "explorer.exe"
                else: self._show(self._rng.choice(["apple.com", "samsung.com", "New tab"]))
            elif keys == ("alt", "left") and self._history: self.title = self._history.pop()
            elif keys == ("ctrl", "s"): self._show("Save As")
            elif keys == ("alt", "f4"): self.title, self.process = "Program Manager", "explorer.exe"
        elif name == "press":
            key = str(payload).lower()
            if key == "win": self._address_bar, self._buffer = True, ""
            elif key == "tab": self._tabbed += 1
            elif key in ("enter", "return"):
                if self._address_bar: self._finish_typing()
                elif self._interstitial_tabs:
                    self._tabbed = 0
                    if self._rng.random() < 0.8: self._clear_interstitial()
                elif self._tabbed and self.process == "msedge.exe": self._follow_link()
            elif key == "f5" and self.process == "msedge.exe": self._navigate(self._history[-1] if self._history else "")
            elif key == "escape": self._address_bar = False
        elif name == "write":
            text = str(payload)
            if self._address_bar: self._buffer += text
            elif self._interstitial_tabs:
                self._buffer += text
                if "thisisunsafe" in self._buffer.replace(" ", "").lower(): self._clear_interstitial()

    def _follow_link(self) -> None:
        """Tab then Enter: sometimes a link, sometimes a button that does nothing, sometimes a dead host."""
        self._tabbed = 0
        roll = self._rng.random()
        if roll > self._link_hit_rate: return  # focus was on a button or an input: nothing happens
        self._history.append(self.title)
        page = self._rng.choice(["support", "products", "about", "pricing", "news", "store"])
        if self._rng.random() < 0.25: self._show(f"{page}.{self._host.split('.')[-1]} can't be reached")
        elif self._rng.random() < 0.3:
            self._interstitial_tabs, self._pending_host = 1, f"{self._host}/{page}"
            self._show("Privacy error")
        else: self._show(f"{page} - {self._host.split('/')[0]}")

    def _launch(self, app: str = "browser") -> None:
        expected = {"browser": "msedge.exe", "word": "winword.exe"}[app]
        if self.process != expected:
            self._opening, self._pending = app, max(1, self._startup_polls)

    def _clear_interstitial(self) -> None:
        self._interstitial_tabs, self._buffer, self._tabbed = 0, "", 0
        self._show(getattr(self, "_pending_host", "apple.com").split("/")[0])

    def _finish_typing(self) -> None:
        text, self._address_bar, self._buffer = self._buffer.strip(), False, ""
        lowered = text.lower()
        if any(word in lowered for word in ("word", "winword")): self._launch("word")
        elif self.process == "msedge.exe": self._navigate(text)
        elif any(word in lowered for word in ("edge", "msedge", "chrome")): self._launch("browser")
