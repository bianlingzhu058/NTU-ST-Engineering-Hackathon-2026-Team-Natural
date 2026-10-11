"""Windows desktop state read through user32/kernel32, plus this process's own cost.

Why this exists. Without it the agent is blind: it presses Win+1 and starts typing a URL
whether or not a browser ever appeared, and on the organisers' mock sites (expired
certificates) it types into a "Your connection isn't private" interstitial. Blind input is
what makes a run look broken in the very logs that are being scored.

Everything here is read-only: window title, foreground process image name, and our own CPU
and memory counters. No process is created, enumerated or terminated, so nothing in this
module can put a non-explorer parent into Sysmon. Every call is wrapped: an API failure
returns a neutral value and the run continues.

One detail that matters for the telemetry criterion itself. Resolving a window to its process
needs OpenProcess, and a verbose Sysmon configuration logs that as Event ID 10 (ProcessAccess).
Doing it on every poll would put thousands of ProcessAccess events from our process against
msedge.exe into the log, which reads like reconnaissance, not like a person browsing. So the
result is cached per window handle: a handful of lookups per run instead of thousands. Set
`perception.use_process_lookup: false` in the config to use window titles alone and issue none
at all.
"""
import ctypes
from ctypes import wintypes
import sys

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class _MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


class WindowsDesktop:
    """Reports the foreground window and this process's resource counters."""
    available = True

    def __init__(self, user32=None, kernel32=None, psapi=None, use_process_lookup: bool = True,
                 cache_limit: int = 32):
        if user32 is None and not sys.platform.startswith("win"):
            raise RuntimeError("WindowsDesktop only runs on Windows")
        self._u = user32 or ctypes.windll.user32
        self._k = kernel32 or ctypes.windll.kernel32
        self._p = psapi or getattr(ctypes.windll, "psapi", self._k)
        self._use_process_lookup, self._cache_limit = use_process_lookup, cache_limit
        self._cache: dict[int, str] = {}
        self.lookups = 0  # counted so the run can report how few ProcessAccess events it caused

    def foreground_title(self) -> str:
        """Title bar text of the focused window, or "" when it cannot be read."""
        try:
            handle = self._u.GetForegroundWindow()
            if not handle: return ""
            buffer = ctypes.create_unicode_buffer(512)
            self._u.GetWindowTextW(handle, buffer, 512)
            return buffer.value or ""
        except Exception:
            return ""

    def foreground_process(self) -> str:
        """Image file name of the focused window's process, lower case, or "" on failure.

        Cached per window handle: one OpenProcess per window per run, not one per poll.
        """
        if not self._use_process_lookup: return ""
        try:
            handle = self._u.GetForegroundWindow()
            if not handle: return ""
            key = int(handle)
            if key in self._cache: return self._cache[key]
            if len(self._cache) >= self._cache_limit: self._cache.clear()
            self._cache[key] = ""  # remember the window even if the lookup below fails
            self.lookups += 1
            pid = wintypes.DWORD()
            self._u.GetWindowThreadProcessId(handle, ctypes.byref(pid))
            proc = self._k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not proc: return ""
            try:
                buffer, size = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
                if not self._k.QueryFullProcessImageNameW(proc, 0, buffer, ctypes.byref(size)): return ""
                self._cache[key] = buffer.value.replace("\\", "/").rsplit("/", 1)[-1].lower()
                return self._cache[key]
            finally:
                self._k.CloseHandle(proc)
        except Exception:
            return ""

    def metrics(self) -> dict[str, float]:
        """Our own CPU seconds since the last call and current memory, for the resource criterion."""
        try:
            handle = self._k.GetCurrentProcess()
            times = [wintypes.FILETIME() for _ in range(4)]
            self._k.GetProcessTimes(handle, *[ctypes.byref(t) for t in times])
            cpu = sum((t.dwHighDateTime << 32 | t.dwLowDateTime) for t in times[2:]) / 1e7
            counters = _MEMORY_COUNTERS(); counters.cb = ctypes.sizeof(counters)
            self._p.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
            return {"cpu_seconds": round(cpu, 3), "working_set_mb": round(counters.WorkingSetSize / 2 ** 20, 2),
                    "private_bytes_mb": round(counters.PagefileUsage / 2 ** 20, 2)}
        except Exception:
            return {}


class BlindDesktop:
    """Stand-in when introspection is off or unavailable: every reading is unknown."""
    available = False
    def foreground_title(self) -> str: return ""
    def foreground_process(self) -> str: return ""
    def metrics(self) -> dict[str, float]: return {}
