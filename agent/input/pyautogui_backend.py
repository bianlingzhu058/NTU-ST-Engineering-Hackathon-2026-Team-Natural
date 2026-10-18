"""PyAutoGUI adapter, the sole module importing the GUI automation library.

Kept for development on a laptop with pip. The VM runtime uses
``sendinput_backend`` instead, which needs only the standard library.
"""
from ..interfaces import InputBackend


class PyAutoGuiBackend(InputBackend):
    """Adapts basic keyboard and pointer operations to PyAutoGUI."""
    def __init__(self):
        import pyautogui
        self._gui = pyautogui
        self._gui.PAUSE = 0
        self._gui.MINIMUM_DURATION = 0
        self._gui.FAILSAFE = False  # the runner has its own stop file; corner moves must not abort

    def press(self, key: str) -> None: self._gui.press(key, interval=0)
    def hotkey(self, *keys: str) -> None: self._gui.hotkey(*keys, interval=0)
    def release_modifiers(self) -> None:
        for key in ("winleft", "ctrl", "alt", "shift"): self._gui.keyUp(key)
    def write(self, text: str) -> None: self._gui.write(text, interval=0)
    def move_to(self, x: float, y: float) -> None: self._gui.moveTo(x, y, duration=0)
    def click(self, x=None, y=None) -> None: self._gui.click(x=x, y=y)
    def scroll(self, amount: int) -> None: self._gui.scroll(amount)
    def position(self) -> tuple[int, int]: p = self._gui.position(); return (int(p.x), int(p.y))
    def screen_size(self) -> tuple[int, int]: s = self._gui.size(); return (int(s.width), int(s.height))
