"""Point-form responsibility: turn JSONL action logs into concise Markdown summaries.

- Groups records by run ID and preserves the synthetic marker.
- Reports event counts and time span without copying event payloads.
- Writes reports to reports/generated/ by default, which is ignored by Git.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent


def build_reports(source: Path, destination: Path) -> list[Path]:
    """Read JSONL records and write one Markdown summary per run ID."""
    groups: dict[str, list[dict]] = {}
    with source.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
            run_id = record.get("run_id")
            if not run_id:
                raise ValueError(f"Missing run_id on line {line_number}")
            groups.setdefault(str(run_id), []).append(record)

    destination.mkdir(parents=True, exist_ok=True)
    written = []
    for run_id, records in groups.items():
        timestamps = [str(record.get("timestamp", "")) for record in records]
        events = Counter(str(record.get("event", "unspecified")) for record in records)
        scenarios = sorted({str(record["objective"]) for record in records if record.get("objective")})
        synthetic = all(record.get("synthetic") is True for record in records)
        safe_run_id = re.sub(r"[^A-Za-z0-9_-]", "_", run_id)[:100] or "unknown-run"
        report = destination / f"{safe_run_id}.md"
        lines = [
            f"# Run report: {run_id}", "", f"- Synthetic activity: {'yes' if synthetic else 'no / mixed'}",
            f"- First recorded timestamp: {min(filter(None, timestamps), default='unknown')}",
            f"- Last recorded timestamp: {max(filter(None, timestamps), default='unknown')}",
            f"- Objectives observed: {', '.join(scenarios) if scenarios else 'not recorded'}", "",
            "## Event counts", "",
        ]
        lines.extend(f"- `{event}`: {count}" for event, count in sorted(events.items()))
        lines.extend(["", "Correlate this run ID and its timestamps with authorized test VM telemetry.", ""])
        report.write_text("\n".join(lines), encoding="utf-8")
        written.append(report)
    return written


def main() -> None:
    """Parse command-line options and create run summaries."""
    parser = argparse.ArgumentParser(prog="python -m reports", description="Summarize JSONL synthetic activity logs.")
    parser.add_argument("source", nargs="?", type=Path, default=ROOT / "logs" / "actions.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "generated")
    args = parser.parse_args()
    try:
        reports = build_reports(args.source, args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if not reports:
        print("No run records found.")
    else:
        for report in reports:
            print(report)


if __name__ == "__main__":
    main()
