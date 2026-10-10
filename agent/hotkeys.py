"""Windows global hotkeys used for keyboard-only operator controls."""
from __future__ import annotations

import ctypes
import sys
import threading
from collections.abc import Callable


class GlobalHotkeys:
    """Register Ctrl+Alt+F9 (start) and Ctrl+Alt+F10 (stop) on Windows."""

    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_NOREPEAT = 0x4000
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012
    VK_F9 = 0x78
    VK_F10 = 0x79

    def __init__(self, on_start: Callable[[], None] | None = None,
                 on_stop: Callable[[], None] | None = None):
        self._callbacks = {1: on_start, 2: on_stop}
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._error: str | None = None
        self._thread_id = 0

    def start(self) -> bool:
        """Start listening. Returns False if unsupported or registration fails."""
        if not sys.platform.startswith("win"):
            return False
        if self._thread and self._thread.is_alive():
            return self._error is None
        self._ready.clear()
        self._error = None
        self._thread = threading.Thread(target=self._listen, name="operator-hotkeys", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2)
        return self._ready.is_set() and self._error is None and self._thread.is_alive()

    def stop(self) -> None:
        """Unregister hotkeys and stop the listener thread."""
        if self._thread and self._thread.is_alive() and self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)
            self._thread.join(timeout=2)

    def _listen(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        modifiers = self.MOD_CONTROL | self.MOD_ALT | self.MOD_NOREPEAT
        registered = []
        for hotkey_id, key in ((1, self.VK_F9), (2, self.VK_F10)):
            if self._callbacks[hotkey_id] is not None:
                if not user32.RegisterHotKey(None, hotkey_id, modifiers, key):
                    self._error = f"Could not register Ctrl+Alt+F{9 if hotkey_id == 1 else 10}; it may be in use."
                    break
                registered.append(hotkey_id)
        self._ready.set()
        if self._error is None:
            class MSG(ctypes.Structure):
                _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint),
                            ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_ssize_t),
                            ("time", ctypes.c_uint), ("pt_x", ctypes.c_long),
                            ("pt_y", ctypes.c_long), ("lPrivate", ctypes.c_uint)]

            msg = MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == self.WM_HOTKEY:
                    callback = self._callbacks.get(int(msg.wParam))
                    if callback:
                        try:
                            callback()
                        except Exception:
                            pass
        for hotkey_id in registered:
            user32.UnregisterHotKey(None, hotkey_id)
        self._thread_id = 0
