"""Read-only Win32 window-state sensing (standard library ctypes only).

Reads the *title of the foreground window* through user32 — the same accessibility
layer that screen readers use. It never reads pixels: no screen capture, no OCR.
That is deliberate. Capturing the screen is what spyware/RATs do (an EDR red flag,
Process Authenticity) and it spikes CPU (Resource Efficiency); reading a window
title costs nothing and leaves no such footprint. The agent uses it only to confirm
the right application window is actually in front before it starts typing, which
makes launches reliable without "seeing" the screen.

Off Windows (dry runs, CI, this sandbox) the sensor is inert: ``available`` is
False and every query returns None, so callers fall back to their fixed waits and
nothing breaks. ``title_provider`` and ``user32`` are injectable so the logic can
be unit-tested on any platform.
"""
import ctypes
import sys
from typing import Any, Optional


class WindowSensor:
    """Confirms which application window is in the foreground, by title.

    Usage: ``foreground_matches(["Edge"])`` -> True / False / None. A None result
    means sensing is unavailable on this platform; the caller should simply proceed
    as it would have without sensing. No method ever raises or blocks.
    """

    def __init__(self, user32: Any = None, platform: Optional[str] = None,
                 title_provider: Optional[Any] = None) -> None:
        # title_provider is a zero-arg callable returning the current foreground
        # title; used by tests so the Win32 buffer plumbing need not be faked.
        self._provider = title_provider
        if title_provider is not None:
            self._u, self.available = None, True
            return
        plat = platform if platform is not None else sys.platform
        if user32 is None:
            if not plat.startswith("win"):
                self._u, self.available = None, False   # inert off Windows
                return
            user32 = ctypes.windll.user32
        self._u, self.available = user32, True

    def foreground_title(self) -> Optional[str]:
        """Title of the window currently in front; "" if none; None if unavailable."""
        if self._provider is not None:
            try:
                return str(self._provider())
            except Exception:
                return None
        if not self.available or self._u is None:
            return None
        try:
            hwnd = self._u.GetForegroundWindow()
            if not hwnd:
                return ""
            length = int(self._u.GetWindowTextLengthW(hwnd))
            buf = ctypes.create_unicode_buffer(length + 1)
            self._u.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:
            return None

    def foreground_matches(self, needles: Any) -> Optional[bool]:
        """True/False if any needle (case-insensitive substring) is in the foreground
        title; None if sensing is unavailable (caller then proceeds unconditionally)."""
        title = self.foreground_title()
        if title is None:
            return None
        if isinstance(needles, str):
            needles = [needles]
        low = title.lower()
        return any(str(n).lower() in low for n in needles if n)
