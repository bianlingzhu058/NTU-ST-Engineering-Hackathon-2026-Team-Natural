# Operator interface

- `__main__.py` — Tkinter entry point; launch with `python -m ui`.
- Defaults to dry-run mode. Real desktop input requires explicit opt-in and VM authorization acknowledgement.
- Shows the active run ID and status, and requests stop using the runner's configured stop file.
- Delegates scenario execution to `agent.app.build_app()` rather than duplicating skill logic.
