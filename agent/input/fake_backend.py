"""In-memory input backend for dry runs and unit tests."""
from typing import Any
from ..interfaces import InputBackend


class FakeInputBackend(InputBackend):
    """Records input operations without controlling a real desktop."""
    def __init__(self, screen: tuple[int, int] = (1920, 1080)):
        self.calls: list[tuple[str, Any]] = []
        self._screen, self._pos = screen, (screen[0] // 2, screen[1] // 2)
    def press(self, key: str) -> None: self.calls.append(("press", key))
    def hotkey(self, *keys: str) -> None: self.calls.append(("hotkey", keys))
    def release_modifiers(self) -> None: self.calls.append(("release_modifiers", ()))
    def write(self, text: str) -> None: self.calls.append(("write", text))
    def key_down(self, key: str) -> None: self.calls.append(("key_down", key))
    def key_up(self, key: str) -> None:
        self.calls.append(("key_up", key))
        # Legacy-compatible record so existing assertions still see the net keystroke:
        # a single character reads as a typed char, a named key reads as a press.
        self.calls.append(("write", key) if len(key) == 1 else ("press", key))
    def move_to(self, x: float, y: float) -> None:
        self._pos = (int(x), int(y)); self.calls.append(("move_to", self._pos))
    def click(self, x=None, y=None) -> None:
        if x is not None and y is not None: self._pos = (int(x), int(y))
        self.calls.append(("click", self._pos))
    def scroll(self, amount: int) -> None: self.calls.append(("scroll", amount))
    def position(self) -> tuple[int, int]: return self._pos
    def screen_size(self) -> tuple[int, int]: return self._screen
