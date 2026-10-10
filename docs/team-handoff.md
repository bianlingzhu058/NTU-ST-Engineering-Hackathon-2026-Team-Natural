# Team handoff: current implementation

This document describes what is present in the repository today. It separates implemented behavior from future work and maps every project file and folder to its purpose.

## Product status

The project has a small local Tkinter desktop interface and a Python runtime behind it. The desktop interface is the main operator entry point; the `python -m agent` CLI remains available for development and troubleshooting. The interface is a source-code application launched from a terminal, not a packaged installer or standalone executable.

## Implemented

- Scenario definitions are loaded from YAML files in `config/objectives/`.
- The operator interface lists available scenarios, accepts a run duration from greater than 0 up to 120 minutes, and starts or requests a stop for one selected scenario.
- The interface starts in dry-run mode. Dry runs use the fake input backend and do not send keyboard or pointer input to the desktop.
- Desktop input is an explicit opt-in in the interface, with a checkbox confirming the test VM is authorized and unlocked.
- The runner checks its time budget and stop file between scenarios, then repeats the selected scenario. A single scenario can make the overall run exceed the requested duration. Stop is cooperative: the current scenario/action sequence may finish before the runner checks the stop condition.
- Scenario skills cover opening/closing an application, entering and saving simple document text, navigating/searching a browser, finding text on a page, and scrolling.
- Keyboard, pointer, scrolling, and reading pauses use shared configurable timing helpers. The fake backend can record these operations for dry runs.
- Action records are appended to `logs/actions.jsonl`. Records include a UTC timestamp, run ID, and `synthetic: true` marker. The logger creates the directory/file when it writes the first event.
- `python -m reports` groups JSONL records by run ID and writes a compact Markdown summary into `reports/generated/`.
- The development CLI can list scenarios, execute one dry-run scenario, or run the runner from a terminal.
- Two analysis utilities can inspect process-creation CSV data and summarize durations from supported JSONL/CSV input.

## Not implemented or not yet complete

- There is no packaged Windows installer, executable, or double-click launcher. Run the desktop interface from the repository with `python -m ui`.
- The interface has no pause/resume control, progress bar, scenario details/preview pane, run history browser, or report viewer.
- The reports tool summarizes this harness's action log only. It does not collect, parse, or correlate Windows Event Log or Sysmon data automatically.
- There is no email workflow, file download workflow, or general office-suite integration. The current office example is a basic text-editor scenario.
- The scenario `office_worker.yaml` still contains placeholder body text. Its `%USERPROFILE%` path is typed literally; the current parameter substitution does not expand Windows environment variables.
- Browser skills do not identify or click arbitrary page links. Browser interaction is limited to address-bar navigation/search, browser find, and scrolling.
- App launch and desktop actions depend on the target Windows VM's installed applications, UI language, screen state, and unlocked interactive session. They have not been validated against every VM image.
- The project does not disguise its automation or implement process-lineage concealment. The UI is launched with Python, and run records are labeled synthetic for authorized monitoring validation.
- The current tests cover timing, typing, objective loading/runner selection, and a source constraint. They do not cover the Tkinter UI or report-generation module.
- No tests or live 15-minute VM run are claimed by this handoff document.

## Start and operate

1. Use Python 3.12.10 (64-bit) and create `.venv31210` with `py -3.12 -m venv .venv31210`.
   Activate the environment, then install dependencies with `python -m pip install -r requirements.txt`.
2. From the repository root, start the desktop interface with `python -m ui`.
3. Choose a scenario and duration. Leave dry-run selected for a preview that does not control the desktop.
4. For an authorized desktop run, deselect dry-run and confirm that the VM is authorized and unlocked.
5. Use **Stop run** to request a stop. The current scenario may need to reach a pacing/runner boundary before it exits.
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
- `agent/skills/browser.py` — URL navigation, address-bar search, browser find, and page scrolling skills.
- `agent/skills/launch.py` — opens an app from Windows UI and closes the foreground app.
- `agent/skills/office.py` — types simple document content and invokes Save As.

#### `agent/objectives/` — YAML plan execution

- `agent/objectives/__init__.py` — package marker.
- `agent/objectives/yaml_objective.py` — expands plan parameters and runs registered skills in order.

### `config/` — runtime settings and scenario definitions

- `config/default.yaml` — timing ranges, typo rate, pointer/scroll settings, default duration, stop-file path, and action-log path.
- `config/objectives/` — folder of scenario YAML definitions loaded when the app starts.
- `config/objectives/idle_browse.yaml` — opens Edge, visits `example.com`, scrolls, then closes the app.
- `config/objectives/office_worker.yaml` — opens Notepad, enters sample document text, attempts Save As, then closes the app; body/path need cleanup as described above.
- `config/objectives/research_topic.yaml` — opens Edge, searches one configured query, scrolls, then closes the app.

### `ui/` — primary operator interface

- `ui/README.md` — UI behavior and launch notes.
- `ui/__main__.py` — Tkinter desktop window for selecting scenario/duration, enabling dry-run or authorized desktop input, showing run ID/status, stopping, and waiting for a clean stop on window close.

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

- `tests/test_no_banned_calls.py` — scans runtime sources for selected process launch/kill APIs.
- `tests/test_runner.py` — checks YAML scenario loading and a zero-duration runner call.
- `tests/test_timing.py` — checks variability in the lognormal delay sampler.
- `tests/test_typing.py` — checks fake-backend correction behavior when typo probability is 100%.

### `tools/` — offline analysis helpers

- `tools/sysmon_parent_checker.py` — prints Event ID 1 process image and parent image fields from a CSV export.
- `tools/timing_analyzer.py` — calculates summary timing statistics from supported JSONL or CSV data.

### Local-only environment

- `.venv31210/` — local Python 3.12.10 virtual environment when present; ignored by Git and should be recreated per machine rather than committed. Recreate it when changing Python versions.
- `.git/` — Git's repository metadata; not application source.
