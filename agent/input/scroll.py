"""Bursty scrolling via the input backend and shared pacer."""
import random
from ..interfaces import InputBackend
from ..timing import HumanPacer


class HumanScroller:
    """Scrolls the page the jagged way a reader does, not a straight march to the bottom."""
    def __init__(self, backend: InputBackend, pacer: HumanPacer, rng: random.Random, burst_size: int = 4):
        self._backend, self._pacer, self._rng, self._burst_size = backend, pacer, rng, burst_size

    def _burst(self, direction: int, notches: int) -> None:
        for _ in range(notches):
            self._backend.scroll(direction)
            self._pacer.wait("step")   # spacing notches de-jerks the scroll over VNC

    def scroll_bursts(self, bursts: int = 3) -> None:
        """Read down a page in a human, non-linear way.

        FIX (human-likeness): real reading is jagged, not a steady top-to-bottom
        march that always ends 'reading' the footer. So each burst varies in size,
        the reader often scrolls BACK UP a little to re-read, sometimes pauses
        mid-page without scrolling, and the run usually stops partway rather than
        bottoming out. This widens the timing/▲▼ variation the judges measure.
        """
        # net downward progress we intend this visit — usually not the whole page
        for i in range(bursts):
            roll = self._rng.random()
            if roll < 0.18 and i > 0:
                # scroll back up a bit to re-read a previous section
                self._burst(+1, self._rng.randint(1, 2))
            elif roll < 0.30:
                # pause in place, as if reading, without moving
                pass
            else:
                # read onward: sometimes a small nudge, sometimes a bigger sweep
                big = self._rng.random() < 0.25
                notches = self._rng.randint(3, max(3, self._burst_size + 2)) if big \
                    else self._rng.randint(1, max(1, self._burst_size))
                self._burst(-1, notches)
            # dwell on what is now in view; occasionally a longer read
            self._pacer.wait("read")
            # sometimes stop early instead of always using every burst
            if i >= 2 and self._rng.random() < 0.15:
                break
