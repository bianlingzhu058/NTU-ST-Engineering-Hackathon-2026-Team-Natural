"""In-memory input backend for dry runs and unit tests."""
from typing import Any
from ..interfaces import InputBackend


class FakeInputBackend(InputBackend):
    """Records input operations without controlling a real desktop."""
    def __init__(self): self.calls: list[tuple[str, Any]] = []
    def press(self, key: str) -> None: self.calls.append(("press", key))
    def hotkey(self, *keys: str) -> None: self.calls.append(("hotkey", keys))
    def write(self, text: str) -> None: self.calls.append(("write", text))
    def move_to(self, x: float, y: float) -> None: self.calls.append(("move_to", (x, y)))
    def click(self, x=None, y=None) -> None: self.calls.append(("click", (x, y)))
    def scroll(self, amount: int) -> None: self.calls.append(("scroll", amount))
