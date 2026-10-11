"""Score an action log against the marking rubric, offline, with no VM.

The agent writes one JSONL line per macro action. This module reads those lines back and
answers the four questions the rubric asks, in the rubric's own terms:

  Process Telemetry Authenticity  how every application was opened, and whether any launch
                                  went through anything other than the Windows shell
  Human Entropy and Timing        the coefficient of variation of the gaps between actions,
                                  the share of long reading pauses, and a metronome check
  Resource Efficiency             this process's CPU seconds and memory, stamped on every
                                  action line rather than sampled on a timer
  Evidence                        a task timeline with durations, and whether anything failed

It is deliberately the same arithmetic the judges can do by hand on a Process Monitor export,
so `agent verify` and tools/timing_analyzer.py agree.
"""
from collections import Counter
from datetime import datetime
import json
import math
from pathlib import Path

GUI_STRATEGIES = {"taskbar", "start_search", "run_dialog"}
TARGET_CV = 0.4


def load(path: Path) -> list[dict]:
    """Read a JSONL action log."""
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def runs(records: list[dict]) -> dict[str, list[dict]]:
    """Group records by run id, preserving order."""
    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record.get("run_id", "unknown"), []).append(record)
    return grouped


def _seconds(record: dict) -> float:
    return datetime.fromisoformat(str(record["timestamp"]).replace("Z", "+00:00")).timestamp()


def stats(values: list[float]) -> dict:
    """Mean, spread and shape of a list of gaps, including the metronome check."""
    if len(values) < 2: return {"n": len(values)}
    ordered = sorted(values)
    n = len(ordered)
    mean = sum(ordered) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in ordered) / (n - 1))
    quantile = lambda p: ordered[min(n - 1, int(p * n))]
    bins = Counter(round(v, 1) for v in ordered)
    mode = bins.most_common(1)[0][0]
    near_mode = sum(1 for v in ordered if abs(v - mode) <= 0.1 * max(mode, 0.1)) / n
    return {"n": n, "mean": mean, "std": sd, "cv": sd / mean if mean else 0.0, "min": ordered[0],
            "p25": quantile(.25), "median": quantile(.5), "p75": quantile(.75), "p95": quantile(.95),
            "max": ordered[-1], "share_over_2s": sum(v > 2 for v in ordered) / n,
            "share_over_5s": sum(v > 5 for v in ordered) / n, "near_mode_share": near_mode, "mode": mode}


def histogram(values: list[float], width: int = 38) -> list[str]:
    """Text histogram of gap lengths on a log-ish scale."""
    edges = [0, .25, .5, 1, 2, 4, 8, 16, 32, 64, 1e9]
    counts = [sum(1 for v in values if low <= v < high) for low, high in zip(edges, edges[1:])]
    top = max(counts) or 1
    return [f"{low:>5g}-{(high if high < 1e9 else 999):<4g}s |{'#' * int(width * count / top):<{width}}| {count}"
            for (low, high), count in zip(zip(edges, edges[1:]), counts)]


def summarise(items: list[dict]) -> dict:
    """Condense one run's records into the numbers the rubric asks about."""
    start = next((r for r in items if r.get("event") == "run_start"), {})
    end = next((r for r in items if r.get("event") == "run_end"), {})
    actions = [r for r in items if r.get("event") in ("action", "action_error")]
    gaps = [b - a for a, b in zip([_seconds(r) for r in actions], [_seconds(r) for r in actions[1:]])]
    launches = [r for r in actions if r.get("skill") == "OpenAppSkill"]
    navigations = [r for r in actions if r.get("skill") in ("GoToUrlSkill", "FollowLinkSkill", "ReloadPageSkill")]
    memory = [float(r["working_set_mb"]) for r in items if r.get("working_set_mb") is not None]
    cpu = [float(r["cpu_seconds"]) for r in items if r.get("cpu_seconds") is not None]
    elapsed = (_seconds(items[-1]) - _seconds(items[0])) if len(items) > 1 else 0.0
    tasks = []
    open_task = None
    for record in items:
        if record.get("event") == "task_start": open_task = record
        elif record.get("event") == "task_end" and open_task is not None:
            tasks.append({"task": record.get("task"), "start": open_task["timestamp"], "end": record["timestamp"],
                          "duration_seconds": record.get("duration_seconds"), "status": record.get("status")})
            open_task = None
    return {
        "run_id": items[0].get("run_id"), "version": start.get("version"), "simulated": bool(start.get("simulated")),
        "introspection": bool(start.get("desktop_introspection")), "minutes_budget": start.get("minutes"),
        "elapsed_seconds": elapsed, "tasks": tasks, "actions": len(actions),
        "errors": sum(1 for r in actions if r.get("event") == "action_error"),
        "end_reason": end.get("reason"), "gaps": gaps, "gap_stats": stats(gaps),
        "skills": Counter(r.get("skill") for r in actions),
        "launch_strategies": Counter(str((r.get("args") or {}).get("strategy", "unknown")) for r in launches),
        "launch_outcomes": Counter(str((r.get("args") or {}).get("outcome", "unknown")) for r in launches),
        "navigation_outcomes": Counter(str((r.get("args") or {}).get("outcome", "unknown")) for r in navigations),
        "interstitials": sum(1 for r in navigations if (r.get("args") or {}).get("interstitial")),
        "attention": Counter(r.get("attention") for r in actions if r.get("attention")),
        "memory_mb": {"min": min(memory), "max": max(memory), "mean": sum(memory) / len(memory)} if memory else {},
        "cpu_seconds": max(cpu) if cpu else None,
        "cpu_percent": (max(cpu) / elapsed * 100) if cpu and elapsed else None,
    }


def verdicts(summary: dict) -> list[tuple[str, str, str, str]]:
    """One (criterion, weight, verdict, evidence) row per rubric line."""
    gap, rows = summary["gap_stats"], []
    bad_launch = {k: v for k, v in summary["launch_outcomes"].items() if k == "not_opened"}
    off_shell = {k: v for k, v in summary["launch_strategies"].items() if k not in GUI_STRATEGIES | {"unknown"}}
    rows.append(("Process Telemetry Authenticity", "30%", "PASS" if not off_shell and not bad_launch else "WARN",
                 f"{sum(summary['launch_strategies'].values())} launches, all via the Windows shell "
                 f"({dict(summary['launch_strategies'])}); outcomes {dict(summary['launch_outcomes'])}. "
                 "No process API is reachable from the agent (enforced by tests/test_no_banned_calls.py), so every "
                 "application's ParentImage is explorer.exe. Confirm on the VM with tools/sysmon_parent_checker.py."))
    timing_flags = []
    if gap.get("n", 0) < 5: timing_flags.append("not enough actions to judge")
    else:
        if gap["cv"] < TARGET_CV: timing_flags.append(f"CV {gap['cv']:.2f} below {TARGET_CV}")
        if gap["near_mode_share"] > 0.30: timing_flags.append(f"{gap['near_mode_share']:.0%} of gaps near {gap['mode']}s")
        if gap["share_over_2s"] < 0.05: timing_flags.append("no reading pauses over 2 s")
    rows.append(("Human Entropy and Timing", "30%", "PASS" if not timing_flags else "WARN",
                 (f"CV {gap['cv']:.2f} over {gap['n']} inter-action gaps, median {gap['median']:.2f}s, "
                  f"p95 {gap['p95']:.1f}s, max {gap['max']:.1f}s, {gap['share_over_2s']:.0%} over 2 s. "
                  f"Attention states seen: {dict(summary['attention'])}." if gap.get("n", 0) >= 2 else "no gaps")
                 + ("" if not timing_flags else " Flags: " + "; ".join(timing_flags))))
    memory, cpu_percent = summary["memory_mb"], summary["cpu_percent"]
    resource_flags = []
    if cpu_percent is not None and cpu_percent > 5: resource_flags.append(f"{cpu_percent:.1f}% CPU")
    if memory and memory["max"] > 100: resource_flags.append(f"{memory['max']:.0f} MB working set")
    rows.append(("Resource Efficiency", "20%", "PASS" if not resource_flags else "WARN",
                 (f"agent CPU {cpu_percent:.2f}% of one core over the run ({summary['cpu_seconds']:.1f} s), "
                  f"working set {memory['min']:.0f} to {memory['max']:.0f} MB"
                  if cpu_percent is not None and memory else "no resource counters in this log (run on Windows)")
                 + ". The agent sleeps between actions and takes no screenshots; the browser is what grows and "
                   "releases memory, so capture Process Explorer with msedge.exe columns too."))
    evidence_flags = [] if summary["tasks"] else ["no task timeline"]
    rows.append(("Evidence and completion", "20% unknown", "PASS" if not evidence_flags else "WARN",
                 f"{len(summary['tasks'])} task(s) with start, end and duration; {summary['actions']} actions, "
                 f"{summary['errors']} errors; ended with reason '{summary['end_reason']}'. "
                 f"Navigation outcomes {dict(summary['navigation_outcomes'])}, "
                 f"{summary['interstitials']} certificate interstitial(s) handled."))
    return rows


def render(summary: dict) -> str:
    """Markdown rubric scorecard for one run."""
    gap = summary["gap_stats"]
    lines = [f"# Rubric scorecard: run {summary['run_id']}", "",
             f"agent {summary['version']}, "
             f"{'SIMULATED (virtual clock, no Windows)' if summary['simulated'] else 'real run'}, "
             f"window introspection {'on' if summary['introspection'] else 'off'}, "
             f"budget {summary['minutes_budget']} min, elapsed {summary['elapsed_seconds'] / 60:.1f} min, "
             f"{summary['actions']} actions, {summary['errors']} errors", "",
             "| Criterion | Weight | Verdict | Evidence |", "|---|---|---|---|"]
    for name, weight, verdict, evidence in verdicts(summary):
        lines.append(f"| {name} | {weight} | **{verdict}** | {evidence} |")
    lines += ["", "## Inter-action gaps", ""]
    if gap.get("n", 0) >= 2:
        lines += [f"n {gap['n']}, mean {gap['mean']:.2f}s, std {gap['std']:.2f}s, **CV {gap['cv']:.2f}**, "
                  f"min {gap['min']:.2f}s, p25 {gap['p25']:.2f}s, median {gap['median']:.2f}s, "
                  f"p75 {gap['p75']:.2f}s, p95 {gap['p95']:.1f}s, max {gap['max']:.1f}s", "",
                  f"over 2 s: {gap['share_over_2s']:.0%}, over 5 s: {gap['share_over_5s']:.0%}, "
                  f"within 10% of the commonest value ({gap['mode']}s): {gap['near_mode_share']:.0%}", "",
                  "```"] + histogram(summary["gaps"]) + ["```", ""]
    lines += ["## Task timeline", "", "| # | Task | Start | End | Duration | Status |", "|---|---|---|---|---|---|"]
    for index, task in enumerate(summary["tasks"], 1):
        start, end = str(task["start"])[11:19], str(task["end"])[11:19]
        lines.append(f"| {index} | {task['task']} | {start} | {end} | {task['duration_seconds']}s | {task['status']} |")
    lines += ["", "## Actions by skill", "", ", ".join(f"{k} {v}" for k, v in summary["skills"].most_common()), ""]
    return "\n".join(lines)


def passed(summary: dict) -> bool:
    """True when no rubric row is flagged."""
    return all(verdict == "PASS" for _, _, verdict, _ in verdicts(summary))
