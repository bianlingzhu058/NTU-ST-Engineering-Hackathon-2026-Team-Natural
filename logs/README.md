# Run logs

- `actions.jsonl` — created by the harness when it records per-action events, including run IDs and the synthetic marker.
- Treat logs as generated test data; do not commit sensitive telemetry or machine-specific output.
- The logger creates this directory and file automatically when a run writes its first event.
