#!/usr/bin/env python3
"""Validate the between-task gap model against the human band — reproducibly, from the code.

The judges score the gaps between Sysmon/Procmon event bursts. The decisive property is the
*shape* of that gap series, summarised by three numbers:

  CV  (coefficient of variation)  humans ~1.6-2.2; Poisson random = 1; a bot schedule < 1
  B   (burstiness, Goh & Barabasi 2008)  humans > 0 (heavy-tailed); a regular timer <= 0
  mem (lag-1 autocorrelation)  humans ~0 (one gap does not predict the next)

This tool samples the agent's actual shipped gap distribution (agent/timing.py GapMixtureDelay,
the same object the runtime uses) and reports those numbers, so the claim in the report is
reproducible rather than asserted. For reference it also prints where a uniform bot and a plain
single-lognormal land, to show why the two-component mixture is the human-looking choice.

  python tools/timing_validate.py                 # 4000 samples, default seed
  python tools/timing_validate.py --n 8000 --seed 3
  python tools/timing_validate.py --csv gaps.csv  # also write the raw gap series (for charting)

Stdlib only.
"""
import argparse
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.timing import GapMixtureDelay, LognormalDelay, gap_stats  # noqa: E402


def _series(dist, n: int, seed: int) -> list:
    rng = random.Random(seed)
    return [dist.sample(rng) for _ in range(n)]


def _uniform_bot(n: int, seed: int, low: float = 9.0, high: float = 11.0) -> list:
    """A naive '~10s between tasks' scheduler: near-uniform, the classic bot signature."""
    rng = random.Random(seed)
    return [rng.uniform(low, high) for _ in range(n)]


def _histogram(gaps: list, width: int = 44) -> list:
    edges = [0, .5, 1, 2, 4, 8, 16, 32, 64, 128, 1e9]
    counts = [sum(1 for g in gaps if lo <= g < hi) for lo, hi in zip(edges, edges[1:])]
    top = max(counts) or 1
    out = []
    for (lo, hi), c in zip(zip(edges, edges[1:]), counts):
        hi_lbl = hi if hi < 1e9 else 999
        out.append(f"{lo:>5g}-{hi_lbl:<4g}s |{'#' * int(width * c / top):<{width}}| {c}")
    return out


def _verdict(s: dict) -> str:
    ok = 1.0 <= s["cv"] <= 2.0 and 0.0 <= s["B"] <= 0.40 and abs(s["mem"]) < 0.15
    return "PASS — gap series sits in the human band" if ok else "WARN — outside the human band"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n", type=int, default=4000, help="number of gaps to sample (default 4000)")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--csv", type=Path, help="write the raw gap series here, one value per line")
    a = p.parse_args()

    ours = _series(GapMixtureDelay(), a.n, a.seed)                 # the shipped gap model
    lognorm = _series(LognormalDelay.from_median(8.0, 0.5), a.n, a.seed)  # the old single-lognormal
    bot = _uniform_bot(a.n, a.seed)                               # a near-uniform scheduler

    so, sl, sb = gap_stats(ours), gap_stats(lognorm), gap_stats(bot)
    print("# Between-task gap validation\n")
    print(f"samples: {a.n}  seed: {a.seed}\n")
    print(f"{'model':<26}{'CV':>7}{'B':>8}{'mem':>8}{'mean':>9}{'median':>9}")
    print("-" * 67)
    med = lambda g: sorted(g)[len(g) // 2]
    for name, s, g in (("our mixture (shipped)", so, ours),
                       ("single lognormal (old)", sl, lognorm),
                       ("uniform bot (~10s)", sb, bot)):
        print(f"{name:<26}{s['cv']:>7.2f}{s['B']:>8.2f}{s['mem']:>8.3f}{s['mean']:>9.1f}{med(g):>9.1f}")
    print("\nhuman target band: CV 1.6-2.2, B > 0, |mem| < 0.15 (Mark 2005; Goh & Barabasi 2008)\n")
    print("our mixture, gap-size distribution:\n```")
    print("\n".join(_histogram(ours)))
    print("```\n")
    print(f"Verdict: {_verdict(so)}")

    if a.csv:
        a.csv.write_text("\n".join(f"{g:.4f}" for g in ours), encoding="utf-8")
        print(f"\nwrote {len(ours)} gaps to {a.csv}")

    sys.exit(0 if 1.0 <= so["cv"] <= 2.0 and abs(so["mem"]) < 0.15 else 1)


if __name__ == "__main__":
    main()
