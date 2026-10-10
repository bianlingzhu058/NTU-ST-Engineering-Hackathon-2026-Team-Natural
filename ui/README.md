# Operator interface

- `__main__.py` — web interface entry point; run `python -m ui`, then open `http://localhost:4000` in a browser on the same VM.
- `web_app.py` — loopback-only HTTP server, run-control API, and objective persistence endpoints.
- `index.html` — browser-based run controls and objective draft editor.
- `desktop.py` — optional legacy Tkinter interface; launch with `python -m ui.desktop`.
- Defaults to dry-run preview mode: **Start run** simulates the selected objective once and reports the number of fake input operations. Real desktop input requires explicit opt-in and VM authorization acknowledgement.
- Shows the active run ID, current scenario and skill, and run status.
- Pause/resume and stop requests take effect at the next input-action boundary.
- Lets an operator customize a draft of a supported browsing objective by adding, reordering, removing, and configuring skills.
- Saves customized objectives as new YAML files in `config/objectives/`; the built-in source objective is not overwritten.
- Skill settings shown by the editor: `open_app` (application name), `go_to_url` (URL), `search` (query), `scroll_and_read` (1–20 bursts), and `find_on_page` (text). `close_app` has no settings.
- Delegates scenario execution to `agent.app.build_app()` rather than duplicating skill logic. Start the server inside the VM whose desktop should be controlled.
