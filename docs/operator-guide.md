# Operator guide

- Use a dedicated, disposable Windows test VM and test account.
- Install Python 3.11 or newer and dependencies from `requirements.txt`.
- Preview a scenario with `python -m agent dry-run --objective research_topic`.
- Run only in an authorized, unlocked test VM; use the CLI until the UI is implemented.
- Stop with the configured stop file (default: `.agent-stop`) and review `logs/actions.jsonl`.
- Correlate action records with VM telemetry using the run ID and timestamps.
- Restore the VM snapshot after a test session.
