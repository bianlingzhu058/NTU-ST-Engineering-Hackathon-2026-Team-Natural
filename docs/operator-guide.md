# Operator guide

- Use a dedicated, disposable Windows test VM and test account.
- Install Python 3.12.10 (64-bit) and create a project virtual environment:
  `py -3.12 -m venv .venv31210`, then activate it and install dependencies with
  `python -m pip install -r requirements.txt`.
- Launch the desktop application from the project folder with `python -m ui`; it starts in dry-run mode.
- Choose a scenario and duration in the interface, then use **Start run**.
- For desktop input, turn off dry-run and confirm the authorized, unlocked test VM prompt.
- Use **Stop run** to request a clean stop; the interface supports durations up to 120 minutes.
- Run only in an authorized, unlocked test VM and review `logs/actions.jsonl` afterward.
- Generate a Markdown summary with `python -m reports`.
- Correlate action records with VM telemetry using the run ID and timestamps.
- Restore the VM snapshot after a test session.
- The `python -m agent ...` commands are available for development and troubleshooting; see the README.
