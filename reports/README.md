# Run reports

- `__main__.py` — reads action JSONL and writes one Markdown summary per run ID.
- Run `python -m reports` to summarize `logs/actions.jsonl`, or pass a source path and `--output` directory.
- Generated summaries go to `reports/generated/`, which is ignored by Git.
- Correlate each report's run ID and timestamps with authorized VM telemetry; keep sensitive telemetry out of Git.
