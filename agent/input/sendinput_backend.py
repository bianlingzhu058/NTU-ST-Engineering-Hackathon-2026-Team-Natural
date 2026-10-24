"""Standard-library input backend for Windows using user32 SendInput.

This is the runtime backend on the VM, where there is no pip. It injects
keyboard and mouse events at the OS level, exactly as PyAutoGUI does
underneath, but with no third-party dependency. ``user32`` is injectable so
the key and mouse plumbing can be unit-tested on any platform.
"""
import ctypes
import sys
from ctypes import wintypes
from ..interfaces import InputBackend

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, KEYEVENTF_SCANCODE = 0x0002, 0x0004, 0x0008
MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE = 0x0001, 0x8000
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, MOUSEEVENTF_WHEEL = 0x0002, 0x0004, 0x0800
WHEEL_DELTA = 120

VK = {  # virtual-key codes for the named keys the skills use
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D, "shift": 0x10, "ctrl": 0x11,
    "alt": 0x12, "pause": 0x13, "esc": 0x1B, "escape": 0x1B, "space": 0x20, "pageup": 0x21,
    "pagedown": 0x22, "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26, "right": 0x27,
    "down": 0x28, "insert": 0x2D, "delete": 0x2E, "win": 0x5B, "winleft": 0x5B, "apps": 0x5D,
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
    **{str(d): 0x30 + d for d in range(10)}, **{c: 0x41 + i for i, c in enumerate("abcdefghijklmnopqrstuvwxyz")},
}


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class SendInputBackend(InputBackend):
    """Injects keyboard and mouse events through user32.SendInput."""
    def __init__(self, user32=None):
        if user32 is None:
            if not sys.platform.startswith("win"):
                raise RuntimeError("SendInputBackend only runs on Windows; use --dry-run elsewhere")
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
        self._u = user32

    # keyboard
    def _key(self, vk: int, up: bool = False) -> None:
        inp = _INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = _KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, None)
        self._u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def _unicode(self, char: str) -> None:
        for flag in (0, KEYEVENTF_KEYUP):
            inp = _INPUT(type=INPUT_KEYBOARD)
            inp.u.ki = _KEYBDINPUT(0, ord(char), KEYEVENTF_UNICODE | flag, 0, None)
            self._u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def set_humanizer(self, typer) -> None:
        """Route press/hotkey through the typing model so every named key and shortcut is held
        down for a human time (about 116 ms) instead of being released instantly."""
        self._human = typer

    def key_event(self, key: str, down: bool) -> None:
        self._key(VK[key.lower()], up=not down)

    def char_event(self, char: str, down: bool) -> None:
        if char == "\n": return self.key_event("enter", down)
        if char == "\t": return self.key_event("tab", down)
        inp = _INPUT(type=INPUT_KEYBOARD)
        inp.u.ki = _KEYBDINPUT(0, ord(char), KEYEVENTF_UNICODE | (0 if down else KEYEVENTF_KEYUP), 0, None)
        self._u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def press(self, key: str) -> None:
        human = getattr(self, "_human", None)
        if human is not None: return human.press(key.lower())
        vk = VK[key.lower()]
        self._key(vk); self._key(vk, up=True)

    def hotkey(self, *keys: str) -> None:
        human = getattr(self, "_human", None)
        if human is not None: return human.combo(*[k.lower() for k in keys])
        vks = [VK[k.lower()] for k in keys]
        for vk in vks: self._key(vk)
        for vk in reversed(vks): self._key(vk, up=True)

    def release_modifiers(self) -> None:
        """Send key-up for every modifier, clearing any that stuck down.

        Over VNC a key-up event can be dropped, leaving a modifier (notably the Windows
        key from a Start-search launch) logically held. The next Tab then becomes Win+Tab
        (Task View) and Ctrl combos become Win+Ctrl+... (new virtual desktops). A key-up on
        a key that is not held is a harmless no-op, so this is safe to call defensively."""
        for name in ("win", "winleft", "ctrl", "alt", "shift"):
            self._key(VK[name], up=True)

    def write(self, text: str) -> None:
        for char in text:
            if char == "\n": self.press("enter")
            elif char == "\t": self.press("tab")
            else: self._unicode(char)

    # mouse
    def screen_size(self) -> tuple[int, int]:
        return int(self._u.GetSystemMetrics(0)), int(self._u.GetSystemMetrics(1))

    def position(self) -> tuple[int, int]:
        pt = wintypes.POINT(); self._u.GetCursorPos(ctypes.byref(pt)); return int(pt.x), int(pt.y)

    def _mouse(self, flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> None:
        inp = _INPUT(type=INPUT_MOUSE)
        inp.u.mi = _MOUSEINPUT(dx, dy, data, flags, 0, None)
        self._u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def move_to(self, x: float, y: float) -> None:
        w, h = self.screen_size()
        nx, ny = int(max(0, min(w - 1, x)) * 65535 / (w - 1)), int(max(0, min(h - 1, y)) * 65535 / (h - 1))
        self._mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, nx, ny)

    def mouse_down(self) -> None:
        self._mouse(MOUSEEVENTF_LEFTDOWN)

    def mouse_up(self) -> None:
        self._mouse(MOUSEEVENTF_LEFTUP)

    def click(self, x=None, y=None) -> None:
        # Kept for compatibility. HumanMouse.click adds a human gap between
        # down and up; a bare down+up here is a fallback for direct callers.
        if x is not None and y is not None: self.move_to(x, y)
        self.mouse_down(); self.mouse_up()

    def scroll(self, amount: int) -> None:
        # positive = wheel up, negative = wheel down, one notch per unit (same sign convention as PyAutoGUI)
        self._mouse(MOUSEEVENTF_WHEEL, data=ctypes.c_uint32(amount * WHEEL_DELTA & 0xFFFFFFFF).value)
