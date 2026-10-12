#!/usr/bin/env python3
"""Measure how human the gaps between actions look, from a Process Monitor CSV or the agent's JSONL.

Judges look at a Procmon timeline filtered to a process and read the gaps between
bursts of activity. This tool does the same thing numerically:

  1. keep events of one process (--process) and of meaningful operations (--ops),
  2. cluster events closer than --gap-threshold seconds into one "burst" (one action),
  3. report the inter-burst gaps: mean, std, coefficient of variation (target > 0.4),
     percentiles, share of long reading pauses, and a near-uniform warning,
  4. optionally compare against a second capture (a real human) with a KS statistic.

Examples:
  python tools/timing_analyzer.py bot_1.csv --process DeskAssist.exe
  python tools/timing_analyzer.py bot_1.csv --process msedge.exe --compare human_kellyn_1.csv --report timing_report.md
  python tools/timing_analyzer.py logs/actions.jsonl
Stdlib only.
"""
import argparse
import csv
import json
import math
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_OPS = ["Process Create", "Process Start", "TCP Connect", "TCP Reconnect", "UDP Send", "WriteFile", "CreateFile"]
TIME_RE = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})(?:[.,](\d+))?\s*([AaPp][Mm])?")


def parse_procmon_time(text: str) -> float | None:
    """'2:03:04.1234567 PM' or '14:03:04.1234567' or '10/11/2026 2:03:04.123 PM' -> seconds since midnight."""
    m = TIME_RE.search(text or "")
    if not m: return None
    h, mi, s, frac, ampm = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) or "0", m.group(5)
    if ampm:
        if ampm.upper() == "PM" and h != 12: h += 12
        if ampm.upper() == "AM" and h == 12: h = 0
    return h * 3600 + mi * 60 + s + float("0." + frac)


def load_procmon(path: Path, process: str | None, ops: list[str] | None) -> list[float]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols = {c.lower(): c for c in reader.fieldnames or []}
        tcol = cols.get("time of day") or cols.get("date & time") or cols.get("time") or next(iter(cols.values()))
        pcol, ocol = cols.get("process name"), cols.get("operation")
        times, last = [], None
        for row in reader:
            if process and pcol and row.get(pcol, "").lower() != process.lower(): continue
            if ops and ocol and row.get(ocol, "") not in ops: continue
            t = parse_procmon_time(row.get(tcol, ""))
            if t is None: continue
            if last is not None and t < last - 1: t += 86400  # midnight rollover
            times.append(t); last = t
    return times


def load_jsonl(path: Path) -> list[float]:
    times = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        rec = json.loads(line)
        if rec.get("event") in ("action", "skill_end", "task_start", "task_end"):
            times.append(datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00")).timestamp())
    return times


def bursts(times: list[float], threshold: float) -> list[float]:
    """Collapse events closer than threshold into one burst; return burst start times."""
    starts = []
    for t in sorted(times):
        if not starts or t - last_t >= threshold: starts.append(t)
        last_t = t
    return starts


def stats(gaps: list[float]) -> dict:
    if len(gaps) < 2: return {"n": len(gaps)}
    gaps = sorted(gaps); n = len(gaps); mean = statistics.mean(gaps); sd = statistics.stdev(gaps)
    q = lambda p: gaps[min(n - 1, int(p * n))]
    mode_bin = max(set(round(g, 1) for g in gaps), key=lambda b: sum(1 for g in gaps if round(g, 1) == b))
    near_mode = sum(1 for g in gaps if abs(g - mode_bin) <= 0.1 * max(mode_bin, 0.1)) / n
    return {"n": n, "mean": mean, "std": sd, "cv": sd / mean if mean else 0.0, "min": gaps[0], "p25": q(.25),
            "median": q(.5), "p75": q(.75), "p95": q(.95), "max": gaps[-1], "share_over_2s": sum(g > 2 for g in gaps) / n,
            "near_mode_share": near_mode, "mode": mode_bin}


def ks_statistic(a: list[float], b: list[float]) -> float:
    """Two-sample Kolmogorov-Smirnov distance (0 identical, 1 disjoint)."""
    a, b = sorted(a), sorted(b); i = j = 0; d = 0.0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]: i += 1
        else: j += 1
        d = max(d, abs(i / len(a) - j / len(b)))
    return d


def histogram(gaps: list[float], width: int = 40) -> list[str]:
    edges = [0, .25, .5, 1, 2, 4, 8, 16, 32, 64, 1e9]
    counts = [sum(1 for g in gaps if lo <= g < hi) for lo, hi in zip(edges, edges[1:])]
    top = max(counts) or 1
    return [f"{lo:>5g}-{(hi if hi < 1e9 else 999):<4g}s |{'#' * int(width * c / top):<{width}}| {c}" for (lo, hi), c in zip(zip(edges, edges[1:]), counts)]


def verdict(s: dict) -> str:
    if s.get("n", 0) < 5: return "NOT ENOUGH BURSTS to judge (need at least 5)"
    flags = []
    if s["cv"] < 0.4: flags.append(f"CV {s['cv']:.2f} is below the 0.4 target: too regular")
    if s["near_mode_share"] > 0.3: flags.append(f"{s['near_mode_share']:.0%} of gaps sit within 10% of {s['mode']}s: metronome pattern")
    if s["share_over_2s"] < 0.05: flags.append("fewer than 5% of gaps exceed 2 s: no reading pauses")
    return "PASS: irregular, human-like gaps" if not flags else "WARN: " + "; ".join(flags)


def analyse(path: Path, process: str | None, ops: list[str] | None, threshold: float) -> tuple[dict, list[float]]:
    times = load_jsonl(path) if path.suffix.lower() == ".jsonl" else load_procmon(path, process, ops)
    starts = bursts(times, threshold)
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    s = stats(gaps); s["events"] = len(times); s["bursts"] = len(starts); s["file"] = path.name
    return s, gaps


def render(s: dict, gaps: list[float]) -> list[str]:
    lines = [f"## {s['file']}", "", f"events kept: {s['events']}, bursts: {s['bursts']}, gaps: {s.get('n', 0)}"]
    if s.get("n", 0) >= 2:
        lines += [f"mean {s['mean']:.2f}s  std {s['std']:.2f}s  **CV {s['cv']:.2f}**  median {s['median']:.2f}s  p95 {s['p95']:.2f}s  max {s['max']:.1f}s",
                  f"gaps over 2 s: {s['share_over_2s']:.0%}", "", "```"] + histogram(gaps) + ["```"]
    lines += ["", f"Verdict: {verdict(s)}", ""]
    return lines


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path", type=Path); p.add_argument("--process", help="Procmon process name to keep, e.g. msedge.exe")
    p.add_argument("--ops", default=",".join(DEFAULT_OPS), help="comma list of Procmon operations to keep, or 'all'")
    p.add_argument("--gap-threshold", type=float, default=0.25, help="seconds; events closer than this form one burst")
    p.add_argument("--compare", type=Path, help="second capture (e.g. a human) to compare against")
    p.add_argument("--compare-process", help="process filter for the --compare file (defaults to --process)")
    p.add_argument("--report", type=Path, help="write a Markdown report here")
    a = p.parse_args()
    ops = None if a.ops.strip().lower() == "all" else [o.strip() for o in a.ops.split(",")]
    s1, g1 = analyse(a.path, a.process, ops, a.gap_threshold)
    out = ["# Timing analysis", ""] + render(s1, g1)
    if a.compare:
        s2, g2 = analyse(a.compare, a.compare_process or a.process, ops, a.gap_threshold)
        out += render(s2, g2)
        if len(g1) >= 2 and len(g2) >= 2:
            ks = ks_statistic(g1, g2)
            out += ["## Comparison", "", f"| | {s1['file']} | {s2['file']} |", "|---|---|---|",
                    f"| CV | {s1['cv']:.2f} | {s2['cv']:.2f} |", f"| median gap | {s1['median']:.2f}s | {s2['median']:.2f}s |",
                    f"| p95 gap | {s1['p95']:.2f}s | {s2['p95']:.2f}s |", f"| gaps over 2 s | {s1['share_over_2s']:.0%} | {s2['share_over_2s']:.0%} |",
                    "", f"KS distance between the two gap distributions: {ks:.2f} (below 0.25 = hard to tell apart, above 0.5 = clearly different)", ""]
    text = "\n".join(out)
    print(text)
    if a.report: a.report.write_text(text, encoding="utf-8")
    sys.exit(0 if s1.get("n", 0) >= 5 and s1["cv"] >= 0.4 else 1)


if __name__ == "__main__": main()
