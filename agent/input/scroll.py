"""Reading a page: how far to scroll, how long each screenful holds attention, and the wheel bursts.

  depth      product and hub pages decay by screen as in NN/g 2018 (57% of viewing time on screen
             one, 81% within three); articles follow Chartbeat (10% never scroll, 10% reach the
             end, most stop around 60%).
  dwell      the page's total dwell (a Weibull draw made by the caller) is split across the
             screens viewed in proportion to NN/g's attention shares, so the first screen gets
             the most time.
  wheel      bursts of 2 to 5 notches when reading, 3 to 8 when skimming, 12% upward re-read
             bursts, keyboard Page Down in about 7% of bursts. No field log of desktop wheel
             bursts exists, so these are design values and are labelled so.
  cursor     the pointer is put over the page before the first notch (Windows sends the wheel to
             the window under the cursor), then mostly rests while reading.
"""
import random
from ..behaviour.dist import clamp, ln_mean, ln_median
from ..behaviour.params import P


class HumanScroller:
    """Scrolls and dwells through the backend, mouse and pacer."""
    def __init__(self, backend, pacer, rng: random.Random, mouse=None):
        self._backend, self._pacer, self._rng, self._mouse = backend, pacer, rng, mouse
        self.last_read: dict = {}

    def screens_to_view(self, kind: str) -> int:
        """How many screens below the first this visit reaches."""
        rng = self._rng
        if kind == "article":
            none, end, a, b = P("scroll.depth_news")
            roll = rng.random()
            total_screens = rng.randint(*P("scroll.article_screens"))
            if roll < none: return 0
            if roll < none + end: return total_screens
            return round(rng.betavariate(a, b) * total_screens)
        weights = P("scroll.depth_product")
        return rng.choices(range(len(weights)), weights=weights, k=1)[0]

    def _notch_gap(self, mode: str) -> float:
        if mode == "read":  # Hinckley 2002: slow "reading" mode between notches
            median, sigma, low, high = P("scroll.notch_gap_read_ms")
            return clamp(ln_median(self._rng, median, sigma), low, high) / 1000.0
        mean, sd, floor = P("scroll.notch_gap_ms")  # fast "flick" mode while skimming
        return max(floor, self._rng.gauss(mean, sd)) / 1000.0

    def burst(self, notches: int, direction: int, mode: str = "skim") -> None:
        """One wheel burst; direction -1 scrolls down (same sign convention as before)."""
        for _ in range(notches):
            self._backend.scroll(direction)
            self._pacer.tiny(self._notch_gap(mode))

    def _hand_on_page(self, region) -> None:
        if not self._mouse or not region: return
        left, top, right, bottom = region
        x, y = self._backend.position()
        if not (left <= x <= right and top <= y <= bottom):
            x_lo, x_hi, y_lo, y_hi = P("scroll.hand_region")
            self._mouse.move(self._rng.uniform(left + (right - left) * x_lo, left + (right - left) * x_hi),
                             self._rng.uniform(top + (bottom - top) * y_lo, top + (bottom - top) * y_hi), 80, 80)

    def read_page(self, kind: str, dwell_seconds: float, region=None, stop_check=lambda: False,
                  time_left=lambda: float("inf")) -> dict:
        """Spend ``dwell_seconds`` on a page, scrolling down through the screens a reader would view."""
        rng = self._rng
        # a short visit cannot also be a deep one: each screen viewed needs a few seconds (design)
        depth = min(self.screens_to_view(kind), int(dwell_seconds / P("scroll.min_screen_s")))
        shares = P("scroll.screen_attention")
        weights = [shares[min(i, len(shares) - 1)] for i in range(depth + 1)]
        total_w = sum(weights)
        per_notch_screens = 1.0 / rng.randint(*P("scroll.notches_per_screen"))
        mode = "read" if kind == "article" else "skim"
        bursts = notches_down = ups = keys = 0
        for screen, weight in enumerate(weights):
            if stop_check() or time_left() < 15: break
            dwell = dwell_seconds * weight / total_w
            if self._mouse: self._mouse.idle(dwell, region)
            else: self._pacer.sleep(dwell)
            if screen == depth: break
            self._hand_on_page(region)
            covered = 0.0
            while covered < 1.0 and not stop_check():
                if rng.random() < P("scroll.keyboard_p"):
                    self._backend.key_event("pagedown", True)
                    low, high = P("typing.hold_clamp_ms")
                    self._pacer.tiny(clamp(ln_mean(rng, P("typing.hold_mean_ms"), P("typing.hold_sigma")), low, high) / 1000.0)
                    self._backend.key_event("pagedown", False)
                    covered, keys = covered + 0.875, keys + 1  # Page Down moves about 87.5% of a screen (unverified)
                else:
                    n = rng.choice(P("scroll.burst_read") if mode == "read" else P("scroll.burst_skim"))
                    self.burst(n, -1, mode)
                    covered += n * per_notch_screens
                    notches_down += n
                bursts += 1
                median, sigma, low, high = P("scroll.glance_s")
                self._pacer.sleep(clamp(ln_median(rng, median, sigma), low, high))  # glance at the new lines
                if rng.random() < P("scroll.up_p"):
                    back = rng.randint(*P("scroll.reread_notches"))
                    self.burst(back, 1, "read")
                    covered -= back * per_notch_screens
                    ups += 1
                    median, sigma, low, high = P("scroll.reread_s")
                    self._pacer.sleep(clamp(ln_median(rng, median, sigma), low, high))
        self.last_read = {"kind": kind, "screens": depth, "bursts": bursts, "notches_down": notches_down,
                          "up_bursts": ups, "page_down": keys, "dwell_s": round(dwell_seconds, 1)}
        return self.last_read
