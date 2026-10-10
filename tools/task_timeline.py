#!/usr/bin/env python3
"""Turn the agent's actions.jsonl into the task timeline the organisers asked to see.

Prints a Markdown table per run: task, start, end, duration, status, and the actions inside
each task with their durations. Default: the most recent run in the file.
  python tools/task_timeline.py logs/actions.jsonl [--all-runs] [--report timeline.md]
"""
import argparse
import json
from datetime import datetime
from pathlib import Path


def _t(s: str) -> datetime: return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("path", type=Path, nargs="?", default=Path("logs/actions.jsonl"))
    p.add_argument("--all-runs", action="store_true"); p.add_argument("--report", type=Path)
    a = p.parse_args()
    recs = [json.loads(l) for l in a.path.read_text(encoding="utf-8").splitlines() if l.strip()]
    runs: dict[str, list[dict]] = {}
    for r in recs: runs.setdefault(r.get("run_id", "?"), []).append(r)
    chosen = runs if a.all_runs else {k: runs[k] for k in list(runs)[-1:]}
    out = []
    for run_id, items in chosen.items():
        out += [f"# Run {run_id}", "", "| # | Task | Start (local) | End | Duration | Status | Actions |", "|---|---|---|---|---|---|---|"]
        task_no, start, actions = 0, None, []
        for r in items:
            ev = r.get("event")
            if ev == "task_start": task_no += 1; start = _t(r["timestamp"]); actions = []
            elif ev in ("action", "action_error"): actions.append(f"{r.get('skill')} {r.get('duration_seconds', 0):.0f}s")
            elif ev == "task_end" and start:
                end = _t(r["timestamp"])
                out.append(f"| {task_no} | {r.get('task')} | {start.astimezone().strftime('%H:%M:%S')} | {end.astimezone().strftime('%H:%M:%S')} | "
                           f"{(end - start).total_seconds():.0f}s | {r.get('status')} | {', '.join(actions)} |")
        out.append("")
    text = "\n".join(out); print(text)
    if a.report: a.report.write_text(text, encoding="utf-8")


if __name__ == "__main__": main()
