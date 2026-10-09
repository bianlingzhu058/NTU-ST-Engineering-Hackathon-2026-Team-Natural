"""Summarize timing gaps in harness JSONL or ProcMon CSV input."""
import argparse
import csv
import json
import logging
import statistics
from pathlib import Path


def main() -> None:
    """Print compact mean, deviation, and coefficient of variation."""
    parser = argparse.ArgumentParser(); parser.add_argument("path", type=Path); args = parser.parse_args()
    try:
        if args.path.suffix.lower() == ".jsonl":
            rows = [json.loads(line) for line in args.path.read_text(encoding="utf-8").splitlines()]
            values = [float(row["duration_seconds"]) for row in rows if row.get("duration_seconds") is not None]
        else:
            with args.path.open(encoding="utf-8-sig", newline="") as file: rows = list(csv.DictReader(file))
            values = [float(row["Duration"]) for row in rows if row.get("Duration")]
        if len(values) < 2: raise ValueError("Need at least two durations")
        mean = statistics.mean(values); stdev = statistics.stdev(values)
        logging.info("n=%d mean=%.3f std=%.3f cv=%.3f", len(values), mean, stdev, stdev / mean if mean else 0)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__": main()
