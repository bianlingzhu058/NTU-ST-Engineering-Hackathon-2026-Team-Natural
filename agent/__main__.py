"""Thin development CLI for the synthetic activity harness."""
import argparse
import logging
from .app import build_app


def main() -> None:
    """Parse development commands and delegate to the composition root."""
    parser = argparse.ArgumentParser(prog="agent")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run"); run.add_argument("--objective"); run.add_argument("--minutes", type=float, default=15); run.add_argument("--seed", type=int)
    listing = sub.add_parser("list-objectives")
    dry = sub.add_parser("dry-run"); dry.add_argument("--objective", required=True); dry.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.command == "list-objectives":
        _, _, _, objectives = build_app(dry_run=True)
        for objective in objectives: logging.info("%s (weight %s)", objective.name, objective.weight)
        return
    _, context, runner, _ = build_app(dry_run=args.command == "dry-run", seed=getattr(args, "seed", None))
    if args.command == "dry-run":
        try: runner.run_once(args.objective)
        except ValueError as exc: parser.error(str(exc))
        for call in context.backend.calls: logging.info("synthetic action: %s", call)
        for kind, duration in context.pacer.samples: logging.info("synthetic pacing: %s %.3fs", kind, duration)
    else: runner.run(args.minutes, args.objective)


if __name__ == "__main__": main()
