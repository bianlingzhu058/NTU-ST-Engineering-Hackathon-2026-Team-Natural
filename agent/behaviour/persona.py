"""One simulated person per run.

Population studies report spread between people (typing speed SD 20 WPM, mouse throughput 3.7 to
4.9 bits/s, reading speed SD 51 wpm). A single person is consistent within a session, so these
are drawn once when the run starts and held, rather than re-drawn per action. The persona is
logged on the run_start line so each run's choices are visible in the evidence.
"""
from dataclasses import dataclass, asdict
import random
from .dist import clamp
from .params import P


@dataclass(frozen=True)
class Persona:
    wpm: float                 # typing speed
    base_iki_ms: float         # 12000 / wpm
    throughput: float          # Fitts throughput, bits/s
    intercept_s: float         # Fitts intercept
    curve_side: int            # which way this person's mouse paths bow
    event_hz: float            # mouse move events per second
    reading_wpm: float
    new_tab_p: float           # chance a followed link opens in a new tab

    @classmethod
    def sample(cls, rng: random.Random) -> "Persona":
        low, high = P("typing.wpm_range")
        wpm = rng.uniform(low, high)
        mean, sd, lo, hi = P("read.wpm")
        tab_low, tab_high, n_low, n_high = P("nav.new_tab_persona")
        return cls(
            wpm=round(wpm, 1), base_iki_ms=round(P("typing.iki_per_wpm") / wpm, 1),
            throughput=round(rng.uniform(*P("mouse.throughput_bits_s")), 2),
            intercept_s=round(rng.uniform(*P("mouse.intercept_s")), 3),
            curve_side=rng.choice((-1, 1)), event_hz=round(rng.uniform(*P("mouse.event_hz")), 1),
            reading_wpm=round(clamp(rng.gauss(mean, sd), lo, hi), 1),
            new_tab_p=rng.choices([tab_low, tab_high], weights=[n_low, n_high], k=1)[0])

    def snapshot(self) -> dict:
        return asdict(self)
