"""In-memory input backend for dry runs and unit tests."""
from typing import Any, Callable
from ..interfaces import InputBackend


class FakeInputBackend(InputBackend):
    """Records input operations without controlling a real desktop.

    An optional observer is notified of every call, which is how the simulated desktop in
    ``agent/win/fake_desktop.py`` reacts to keystrokes: that makes a dry run exercise the real
    verification and recovery branches instead of skipping over them.
    """
    def __init__(self, screen: tuple[int, int] = (1920, 1080), observer: Callable[[str, Any], None] | None = None):
        self.calls: list[tuple[str, Any]] = []
        self._screen, self._pos, self._observer = screen, (screen[0] // 2, screen[1] // 2), observer

    def _record(self, name: str, payload: Any) -> None:
        self.calls.append((name, payload))
        if self._observer: self._observer(name, payload)

    def press(self, key: str) -> None: self._record("press", key)
    def hotkey(self, *keys: str) -> None: self._record("hotkey", keys)
    def write(self, text: str) -> None: self._record("write", text)
    def move_to(self, x: float, y: float) -> None:
        self._pos = (int(x), int(y)); self._record("move_to", self._pos)
    def click(self, x=None, y=None) -> None:
        if x is not None and y is not None: self._pos = (int(x), int(y))
        self._record("click", self._pos)
    def scroll(self, amount: int) -> None: self._record("scroll", amount)
    def key_event(self, key: str, down: bool) -> None:
        self._record("key_down" if down else "key_up", key)
        if down: self._record("press", key)  # the simulated desktop reacts to presses
    def char_event(self, char: str, down: bool) -> None:
        self._record("char_down" if down else "char_up", char)
        if down: self._record("write", char)
    def button_event(self, down: bool) -> None:
        self._record("button_down" if down else "button_up", self._pos)
        if not down: self._record("click", self._pos)
    def position(self) -> tuple[int, int]: return self._pos
    def screen_size(self) -> tuple[int, int]: return self._screen
