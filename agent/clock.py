"""Time sources, injected everywhere so a 15 minute run can be replayed offline in a second.

``RealClock`` is what the VM uses. ``VirtualClock`` advances only when something sleeps, so
``agent simulate`` produces a full-length log with realistic timestamps instantly, on Linux,
with no VM. That log is what ``agent verify`` scores against the rubric.
"""
from datetime import datetime, timezone
import time


class RealClock:
    """Wall-clock time and real sleeping."""
    virtual = False
    def monotonic(self) -> float: return time.monotonic()
    def sleep(self, seconds: float) -> None: time.sleep(max(0.0, seconds))
    def now_iso(self) -> str: return datetime.now(timezone.utc).isoformat()


class VirtualClock:
    """Simulated time: sleeping costs nothing but moves the clock and the timestamps."""
    virtual = True
    def __init__(self, start_epoch: float | None = None):
        self._elapsed, self._epoch = 0.0, start_epoch if start_epoch is not None else time.time()
    def monotonic(self) -> float: return self._elapsed
    def sleep(self, seconds: float) -> None: self._elapsed += max(0.0, seconds)
    def now_iso(self) -> str:
        return datetime.fromtimestamp(self._epoch + self._elapsed, timezone.utc).isoformat()
