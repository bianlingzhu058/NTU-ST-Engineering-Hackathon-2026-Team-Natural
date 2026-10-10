# Team handoff: current implementation

This document describes what is present in the repository today. It separates implemented behavior from future work and maps every project file and folder to its purpose.

## Product status

The project has a local web operator interface and Python runtime. Start the server inside the Windows VM with `python -m ui`, then open `http://localhost:4000` in that VM's browser. The server binds to loopback only. The older Tkinter interface is available with `python -m ui.desktop`; the `python -m agent` CLI remains available for development and troubleshooting. The app is source code launched from a terminal, not a packaged installer or standalone executable.

## Implemented

- Scenario definitions are loaded from YAML files in `config/objectives/`.
- The operator interface lists objectives and starts the selected objective. Live runs accept a duration from greater than 0 up to 120 minutes; dry-run previews execute the selected objective once.
- The interface starts in dry-run preview mode. It uses the fake input backend, sends no desktop input, and reports the number of simulated actions.
- The interface shows the current scenario and skill, and pause/resume/stop requests are honored at input-action boundaries.
- The interface can open a draft of a supported browsing objective, add/reorder/remove skills, configure skill inputs, and save the result as a new YAML objective.
- Desktop input is an explicit opt-in in the interface, with a checkbox confirming the test VM is authorized and unlocked.
- The runner checks its time budget between scenarios, then repeats the selected scenario. A single scenario can make the overall run exceed the requested duration. Pause and stop are cooperative and take effect at input-action boundaries.
- Scenario skills cover opening/closing an application, entering and saving simple document text, navigating/searching a browser, finding text on a page, and scrolling.
- Keyboard, pointer, scrolling, and reading pauses use shared configurable timing helpers. The fake backend can record these operations for dry runs.
- Action records are appended to `logs/actions.jsonl`. Records include a UTC timestamp, run ID, and `synthetic: true` marker. The logger creates the directory/file when it writes the first event.
- `python -m reports` groups JSONL records by run ID and writes a compact Markdown summary into `reports/generated/`.
- The development CLI can list scenarios, execute one dry-run scenario, or run the runner from a terminal.
- Two analysis utilities can inspect process-creation CSV data and summarize durations from supported JSONL/CSV input.

## Not implemented or not yet complete

- There is no packaged Windows installer, executable, or double-click launcher. The repository must be present inside the VM for the web UI to control that VM's desktop.
- The interface has no progress bar, scenario details/preview pane, run history browser, or report viewer.
- The reports tool summarizes this harness's action log only. It does not collect, parse, or correlate Windows Event Log or Sysmon data automatically.
- There is no email workflow, file download workflow, or general office-suite integration. The current office example is a basic text-editor scenario.
- The scenario `office_worker.yaml` still contains placeholder body text. Its `%USERPROFILE%` path is typed literally; the current parameter substitution does not expand Windows environment variables.
- Browser skills do not identify or click arbitrary page links. Browser interaction is limited to address-bar navigation/search, browser find, and scrolling.
- App launch and desktop actions depend on the target Windows VM's installed applications, UI language, screen state, and unlocked interactive session. They have not been validated against every VM image.
- The project does not disguise its automation or implement process-lineage concealment. The UI is launched with Python, and run records are labeled synthetic for authorized monitoring validation.
- Tests cover timing, typing, run control, objective loading/runner selection, UI objective storage/validation, and a source constraint. The Tkinter interaction flow and report-generation module are not covered automatically.
- Automated tests and a browsing dry run pass; no live desktop or 15-minute VM run has been performed.

## Start and operate

1. Use Python 3.11 or newer and install dependencies with `pip install -r requirements.txt`.
2. From a terminal inside the VM and the repository root, start the web server with `python -m ui`.
3. Open `http://localhost:4000` in a browser inside that same VM. Choose an objective; dry-run is a single simulated preview.
4. For an authorized desktop run, deselect dry-run and confirm that the VM is authorized and unlocked.
5. Use **Pause/Resume** or **Stop run**; requests take effect at the next input-action boundary.
6. Inspect `logs/actions.jsonl`; optionally run `python -m reports` to create summaries.
7. Correlate run IDs/timestamps with separately collected VM telemetry and restore the VM snapshot after testing.

Development-only CLI examples:

- `python -m agent list-objectives`
- `python -m agent dry-run --objective research_topic`
- `python -m agent run --objective research_topic --minutes 15`

## Repository map

### Root files

- `README.md` — project overview, desktop startup, development commands, authoring guidance, monitoring notes, and short repository map.
- `docs/team-handoff.md` — detailed implementation status, limitations, workflow, and file/folder map.
- `requirements.txt` — Python runtime/development dependencies: PyAutoGUI, PyYAML, and pytest.
- `.gitignore` — excludes Python caches, virtual environments, local config overrides, generated logs/reports, and build output.

### `agent/` — runtime and extension points

- `agent/__init__.py` — makes the runtime importable as a Python package.
- `agent/__main__.py` — development CLI for listing, dry-running, and running scenarios.
- `agent/app.py` — composition root that reads config and wires backend, pacing, skills, logger, and runner.
- `agent/config.py` — YAML settings/objective loading and lightweight objective data validation.
- `agent/interfaces.py` — abstract contracts for input, delays, skills, objectives, and logging.
- `agent/logger.py` — thread-safe JSONL event writer with timestamp, run ID, and synthetic marker.
- `agent/registry.py` — decorator-based skill registry and skill construction.
- `agent/runner.py` — weighted scenario selection, duration loop, objective event logging, and stop-file checks.
- `agent/run_control.py` — thread-safe cooperative pause/stop state checked at input-action boundaries.
- `agent/timing.py` — delay distributions and the shared pacing/wait implementation.

#### `agent/input/` — input adapters and primitives

- `agent/input/__init__.py` — package marker.
- `agent/input/fake_backend.py` — records input calls in memory for dry runs and tests.
- `agent/input/pyautogui_backend.py` — sends keyboard, pointer, and scroll operations through PyAutoGUI.
- `agent/input/keyboard.py` — types text through the backend with configurable typo/correction simulation and pauses.
- `agent/input/mouse.py` — moves through sampled intermediate positions and supports clicks.
- `agent/input/scroll.py` — performs bounded scroll bursts through the backend.

#### `agent/skills/` — reusable scenario actions

- `agent/skills/__init__.py` — imports built-in skill modules so decorators register their skill names.
- `agent/skills/base.py` — shared `SkillContext`, common logging/error wrapper, and base skill.
- `agent/skills/catalog.py` — editor labels, descriptions, and input fields for supported browsing skills.
- `agent/skills/browser.py` — URL navigation, address-bar search, browser find, and page scrolling skills.
- `agent/skills/launch.py` — opens an app from Windows UI and closes the foreground app.
- `agent/skills/office.py` — types simple document content and invokes Save As.

#### `agent/objectives/` — YAML plan execution

- `agent/objectives/__init__.py` — package marker.
- `agent/objectives/yaml_objective.py` — expands plan parameters and runs registered skills in order.
- `agent/objectives/storage.py` — validates and saves UI-authored YAML objectives without overwriting existing ones.

### `config/` — runtime settings and scenario definitions

- `config/default.yaml` — timing ranges, typo rate, pointer/scroll settings, default duration, stop-file path, and action-log path.
- `config/objectives/` — folder of scenario YAML definitions loaded when the app starts.
- `config/objectives/browse_internet.yaml` — default directly runnable web-browsing objective.
- `config/objectives/idle_browse.yaml` — opens Edge, visits `example.com`, scrolls, then closes the app.
- `config/objectives/office_worker.yaml` — opens Notepad, enters sample document text, attempts Save As, then closes the app; body/path need cleanup as described above.
- `config/objectives/research_topic.yaml` — opens Edge, searches one configured query, scrolls, then closes the app.

### `ui/` — primary operator interface

- `ui/README.md` — UI behavior and launch notes.
- `ui/__main__.py` — web server entry point for `python -m ui`.
- `ui/web_app.py` — loopback HTTP server, run-control API, and objective storage endpoints.
- `ui/index.html` — browser UI for running objectives and editing drafts.
- `ui/desktop.py` — optional Tkinter interface.
- `ui/objective_editor.py` — draft editor for adding, configuring, and reordering supported browsing skills, then saving as a new objective.

### `logs/` — generated action records

- `logs/README.md` — describes the generated log and handling of test data.
- `logs/actions.jsonl` — runtime output, ignored by Git and created when the first event is logged; it may not exist in a fresh checkout.

### `reports/` — generated run summaries

- `reports/README.md` — describes the report command and generated output.
- `reports/__main__.py` — parses JSONL events and writes one Markdown summary per run ID.
- `reports/generated/` — runtime output folder, ignored by Git and created when reports are generated.

### `docs/` — teammate and operator documentation

- `docs/team-handoff.md` — this document: implementation status, limitations, workflows, and full file map.
- `docs/operator-guide.md` — concise setup, run, stop, log review, and telemetry-correlation workflow.
- `docs/scenario-authoring.md` — guidance for adding YAML scenarios and reviewing their actions.

### `tests/` — automated checks

- `tests/test_run_control.py` — checks pause/resume and stop requests at cooperative checkpoints.

- `tests/test_no_banned_calls.py` — scans runtime sources for selected process launch/kill APIs.
- `tests/test_runner.py` — checks YAML scenario loading and a zero-duration runner call.
- `tests/test_timing.py` — checks variability in the lognormal delay sampler.
- `tests/test_typing.py` — checks fake-backend correction behavior when typo probability is 100%.

### `tools/` — offline analysis helpers

- `tools/sysmon_parent_checker.py` — prints Event ID 1 process image and parent image fields from a CSV export.
- `tools/timing_analyzer.py` — calculates summary timing statistics from supported JSONL or CSV data.

### Local-only environment

- `.venv311/` — local Python 3.11 virtual environment when present; ignored by Git and should be recreated per machine rather than committed.
- `.git/` — Git's repository metadata; not application source.
