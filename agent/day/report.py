"""Laptop simulation of a workday: fake input, simulated clock, and the checks we care about.

    python -m agent simulate --minutes 15 --seed 3 --show
    python -m agent simulate --minutes 60 --many 30
"""
import collections
import math
import traceback


def _cv(values):
    values = [v for v in values if v > 0]
    if len(values) < 3: return float("nan")
    mean = sum(values) / len(values)
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    return sd / mean


def run_one(root, minutes: float, seed: int):
    from ..app import build_app, run_workday
    _, context, _, _ = build_app(root, sim=True, seed=seed)
    from .workday import Workday
    day = Workday(context, root, minutes, sim=True)
    summary = day.run()
    return day, context, summary


def checks(day, context, summary) -> dict:
    typer, pacer = context.typer, context.pacer
    holds = typer.stats["holds_ms"]
    pauses = [d for k, d in pacer.samples if k not in ("micro", "glide", "keydata") and not k.startswith("break")]
    todo = day.todo
    extra = ("\n\n" + todo.progress) if getattr(todo, "progress", None) else ""
    expected = todo.expected_text(extra)
    calls = context.backend.calls
    return {
        "overrun_s": summary["overrun_s"],
        "todo_page_matches_plan": todo.doc.text == expected,
        "wpm": typer.wpm,
        "key_hold_mean_ms": round(sum(holds) / max(1, len(holds)), 1),
        "backspace_share": round(typer.stats["backspaces"] / max(1, typer.stats["keys"]), 3),
        "pause_cv": round(_cv(pauses), 2),
        "browser_share": summary["app_share"].get("browser", 0.0),
        "apps_left_open": [w.label for w in day.desk.mru if w.app != "harness"],
        "alt_tabs": summary["switches"],
        "keys_sent": sum(1 for c in calls if c[0] in ("press", "write", "hotkey")),
    }


def simulate_cli(root, args) -> None:
    if args.many:
        agg, fails = collections.defaultdict(list), []
        statuses = collections.Counter()
        for seed in range(args.seed, args.seed + args.many):
            try:
                day, context, summary = run_one(root, args.minutes, seed)
            except Exception:
                fails.append((seed, traceback.format_exc().strip().splitlines()[-1]))
                continue
            c = checks(day, context, summary)
            for k, v in c.items():
                if isinstance(v, (int, float)): agg[k].append(v)
            agg["matches"].append(1 if c["todo_page_matches_plan"] else 0)
            agg["left_open"].append(len(c["apps_left_open"]))
            for _, status, _ in summary["items"]: statuses[status] += 1
        print(f"{args.many} runs of {args.minutes} min, crashes: {len(fails)}")
        for seed, err in fails[:5]: print("  crash seed", seed, err)
        for k, vals in agg.items():
            print(f"  {k:24s} min {min(vals):8.2f}  mean {sum(vals)/len(vals):8.2f}  max {max(vals):8.2f}")
        print("  item endings:", dict(statuses))
        return
    day, context, summary = run_one(root, args.minutes, args.seed)
    if args.show:
        for row in day.log_rows:
            t = row.get("t", 0)
            rest = {k: v for k, v in row.items() if k not in ("t",)}
            print(f"{int(t // 60):3d}:{t % 60:04.1f}  {rest}")
    print("\n--- to do list as it ends up on the page ---")
    print(summary["todo_text"])
    print("\n--- files saved ---", summary["files"])
    print("--- breaks ---", summary["breaks"])
    print("--- time share ---", summary["app_share"])
    print("--- checks ---")
    for k, v in checks(day, context, summary).items(): print(f"  {k}: {v}")
