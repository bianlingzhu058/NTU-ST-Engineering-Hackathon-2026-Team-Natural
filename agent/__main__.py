"""Thin CLI: run, simulate, verify, selftest, dry-run, list-objectives. No business logic here.

The double-clicked shortcut on the VM uses `run` (or no arguments at all, through
sitecustomize.py). Everything else is for proving the rubric offline:

  agent simulate --minutes 15     a full-length run on a virtual clock, no Windows needed
  agent verify logs/simulated.jsonl   the rubric scorecard for that log
  agent selftest                  simulate and verify several seeds, exit nonzero on any flag
"""
import argparse
import logging
from pathlib import Path
from .app import build_app, run_desktop
from . import report

ROOT = Path(__file__).resolve().parent.parent


def _simulate(objective: str | None, minutes: float, seed: int | None, log_name: str) -> Path:
    """Run the agent against the simulated desktop on a virtual clock; return the log path."""
    path = ROOT / log_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    config, _, runner, _ = build_app(ROOT, mode="sim", seed=seed, log_name=log_name)
    runner.run(minutes, objective if objective is not None else config.section("runner").get("objective") or None)
    return path


def _verify(path: Path, report_path: Path | None, all_runs: bool) -> bool:
    records = report.load(path)
    grouped = report.runs(records)
    chosen = list(grouped.values()) if all_runs else list(grouped.values())[-1:]
    texts, ok = [], True
    for items in chosen:
        summary = report.summarise(items)
        texts.append(report.render(summary))
        ok = ok and report.passed(summary)
    text = "\n\n".join(texts)
    print(text)
    if report_path: report_path.write_text(text, encoding="utf-8")
    return ok


def main() -> None:
    """Parse commands and delegate to the composition root."""
    parser = argparse.ArgumentParser(prog="agent")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="the judged run: real input, real clock")
    run.add_argument("--objective"); run.add_argument("--minutes", type=float); run.add_argument("--seed", type=int)
    sub.add_parser("list-objectives")
    dry = sub.add_parser("dry-run", help="one objective against the simulated desktop, instantly")
    dry.add_argument("--objective", required=True); dry.add_argument("--seed", type=int, default=1)
    sim = sub.add_parser("simulate", help="a full-length run on a virtual clock, then score it")
    sim.add_argument("--objective"); sim.add_argument("--minutes", type=float, default=15.0)
    sim.add_argument("--seed", type=int); sim.add_argument("--log", default="logs/simulated.jsonl")
    sim.add_argument("--report", type=Path); sim.add_argument("--no-verify", action="store_true")
    ver = sub.add_parser("verify", help="score an action log against the rubric")
    ver.add_argument("path", type=Path, nargs="?", default=ROOT / "logs" / "actions.jsonl")
    ver.add_argument("--report", type=Path); ver.add_argument("--all-runs", action="store_true")
    self_test = sub.add_parser("selftest", help="simulate several seeds and score every one")
    self_test.add_argument("--runs", type=int, default=3); self_test.add_argument("--minutes", type=float, default=15.0)
    self_test.add_argument("--objective"); self_test.add_argument("--report", type=Path)
    args = parser.parse_args()

    if args.command == "run":
        (ROOT / "logs").mkdir(exist_ok=True)  # pythonw.exe has no console: log to a file, never to a missing stderr
        logging.basicConfig(filename=ROOT / "logs" / "agent.log", level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")
        logging.info("run requested: objective=%s minutes=%s", args.objective, args.minutes)
        try:
            run_desktop(args.objective, args.minutes)
        except Exception:
            logging.exception("run ended with an exception")
            raise
        return

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.command == "list-objectives":
        _, _, _, objectives = build_app(ROOT, mode="dry")
        for objective in objectives:
            logging.info("%s (weight %s, %d plan steps)", objective.name, objective.weight, len(objective.plan))
        return

    if args.command == "dry-run":
        _, context, runner, _ = build_app(ROOT, mode="dry", seed=args.seed, log_name="logs/dry_run.jsonl")
        try:
            runner.run_once(args.objective)
        except ValueError as exc:
            parser.error(str(exc))
        for call in context.backend.calls: logging.info("action: %s", call)
        total = sum(seconds for _, seconds in context.pacer.samples)
        logging.info("pacing: %d waits, %.1f s simulated", len(context.pacer.samples), total)
        for kind in sorted({kind for kind, _ in context.pacer.samples}):
            logging.info("  %-6s n=%d", kind, sum(1 for k, _ in context.pacer.samples if k == kind))
        return

    if args.command == "simulate":
        path = _simulate(args.objective, args.minutes, args.seed, args.log)
        logging.info("wrote %s", path)
        if not args.no_verify:
            raise SystemExit(0 if _verify(path, args.report, False) else 1)
        return

    if args.command == "verify":
        raise SystemExit(0 if _verify(args.path, args.report, args.all_runs) else 1)

    rows, failures = [], 0
    for seed in range(1, max(1, args.runs) + 1):
        path = _simulate(args.objective, args.minutes, seed, f"logs/selftest_{seed}.jsonl")
        summary = report.summarise(list(report.runs(report.load(path)).values())[-1])
        gap, ok = summary["gap_stats"], report.passed(summary)
        failures += not ok
        rows.append(f"| {seed} | {len(summary['tasks'])} | {summary['actions']} | {gap.get('cv', 0):.2f} | "
                    f"{gap.get('median', 0):.2f}s | {gap.get('p95', 0):.1f}s | {gap.get('share_over_2s', 0):.0%} | "
                    f"{summary['errors']} | {'PASS' if ok else 'WARN'} |")
    text = "\n".join([f"# Selftest: {args.runs} simulated runs of {args.minutes:g} minutes", "",
                      "| seed | tasks | actions | CV | median gap | p95 gap | over 2 s | errors | verdict |",
                      "|---|---|---|---|---|---|---|---|---|"] + rows +
                     ["", f"{args.runs - failures}/{args.runs} runs clean", ""])
    print(text)
    if args.report: args.report.write_text(text, encoding="utf-8")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__": main()
