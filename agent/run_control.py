"""Thread-safe pause and stop coordination for an active run."""
from __future__ import annotations

from threading import Condition
from typing import Callable


class RunStopped(Exception):
    """Raised at an action boundary when a run has been asked to stop."""


class RunControl:
    """Coordinates cooperative pause and stop requests across runtime threads."""

    def __init__(self, stop_check: Callable[[], bool] = lambda: False) -> None:
        self._condition = Condition()
        self._paused = False
        self._stopped = False
        self._stop_check = stop_check

    @property
    def paused(self) -> bool:
        with self._condition:
            return self._paused and not self._stopped

    @property
    def stopped(self) -> bool:
        with self._condition:
            return self._stopped

    def pause(self) -> None:
        with self._condition:
            if not self._stopped:
                self._paused = True

    def resume(self) -> None:
        with self._condition:
            self._paused = False
            self._condition.notify_all()

    def stop(self) -> None:
        with self._condition:
            self._stopped = True
            self._paused = False
            self._condition.notify_all()

    def checkpoint(self) -> None:
        """Wait out a pause, or raise promptly when stop has been requested."""
        with self._condition:
            if self._stop_check():
                self._stopped = True
                self._paused = False
                self._condition.notify_all()
            while self._paused and not self._stopped:
                self._condition.wait(timeout=0.1)
                if self._stop_check():
                    self._stopped = True
            if self._stopped:
                raise RunStopped
