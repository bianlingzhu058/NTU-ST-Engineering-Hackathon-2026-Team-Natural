"""Thin CLI: run, list-objectives, dry-run. No business logic lives here."""
import argparse
import logging
from pathlib import Path
from .app import build_app, run_desktop


def main() -> None:
    """Parse commands and delegate to the composition root."""
    parser = argparse.ArgumentParser(prog="agent")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run"); run.add_argument("--objective"); run.add_argument("--minutes", type=float); run.add_argument("--seed", type=int)
    sub.add_parser("list-objectives")
    dry = sub.add_parser("dry-run"); dry.add_argument("--objective", required=True); dry.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    if args.command == "run":
        # pythonw.exe has no console: log to a file, never to a missing stderr
        (root / "logs").mkdir(exist_ok=True)
        logging.basicConfig(filename=root / "logs" / "agent.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        run_desktop(args.objective, args.minutes)
        return
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.command == "list-objectives":
        _, _, _, objectives = build_app(dry_run=True)
        for objective in objectives: logging.info("%s (weight %s)", objective.name, objective.weight)
        return
    _, context, runner, _ = build_app(dry_run=True, seed=args.seed)
    try: runner.run_once(args.objective)
    except ValueError as exc: parser.error(str(exc))
    for call in context.backend.calls: logging.info("action: %s", call)
    total = sum(d for _, d in context.pacer.samples)
    logging.info("pacing: %d waits, %.1f s simulated", len(context.pacer.samples), total)
    for kind in sorted({k for k, _ in context.pacer.samples}):
        logging.info("  %-6s n=%d", kind, sum(1 for k, _ in context.pacer.samples if k == kind))


if __name__ == "__main__": main()
