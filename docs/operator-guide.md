# Operator guide

- Use a dedicated, disposable Windows test VM and test account.
- Install Python 3.11 or newer and dependencies from `requirements.txt`.
- From a terminal inside the VM, launch the web server with `python -m ui`, leave it running, and open `http://localhost:4000` in that VM's browser. It starts in dry-run preview mode and listens only on the VM itself.
- In dry-run mode, **Start run** simulates the selected objective once, reports the number of simulated input actions, and writes the event records to `logs/actions.jsonl`. It does not open or control a browser.
- For an authorized VM run, disable dry-run, enter a duration, and use **Start run**. The selected objective repeats within that live run duration.
- Choose `browse_internet` to run the default browsing objective directly, or use **Customize selected...** to create a draft and save it as a new objective YAML file.
- For desktop input, turn off dry-run and confirm the authorized, unlocked test VM prompt.
- Use **Pause**/**Resume** to suspend or continue at the next input-action boundary. The interface shows the current scenario and skill.
- Use **Stop run** to request a clean stop at the next input-action boundary; the interface supports durations up to 120 minutes.
- Run only in an authorized, unlocked test VM and review `logs/actions.jsonl` afterward.
- Generate a Markdown summary with `python -m reports`.
- Correlate action records with VM telemetry using the run ID and timestamps.
- Restore the VM snapshot after a test session.
- The `python -m agent ...` commands are available for development and troubleshooting; see the README.
