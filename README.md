# Synthetic Desktop Activity Harness (DeskAssist)

**Current version: 1.0-research (branch `v1-research`).** Every behaviour number comes from published
research or a public dataset, or is tagged as a design guess, in `agent/behaviour/params.py`.
Start with [`docs/v1-research-design.md`](docs/v1-research-design.md).


- Desktop application for running labeled scenarios in an authorized test VM.
- Writes synthetic run and action records to `logs/actions.jsonl` for monitoring validation.
- Uses a fake input backend for dry runs; Windows desktop runs use PyAutoGUI.

## Start the desktop application

1. Install Python 3.11 or newer.
2. From the project folder, install dependencies:

   ```sh
   pip install -r requirements.txt
   ```

3. Start the operator interface:

   ```sh
   python -m ui
   ```

4. Select a scenario and duration. The interface starts in dry-run mode. To control the desktop, disable dry-run and confirm that the VM is authorized and unlocked.

5. Use **Stop run** to request a clean stop. Review `logs/actions.jsonl` or generate Markdown run summaries with `python -m reports`.

The GUI runs in the foreground. Keep the Windows test VM unlocked during desktop runs.


## VM runtime (no installation)

The judged run uses no pip and no installer. `packaging/build_bundle.sh <python-3.11-embed-amd64.zip>`
(or the path of a previously built `DeskAssist.zip`, whose runtime is reused) produces
`dist/DeskAssist.zip`: the Python embeddable runtime with `pythonw.exe` copied to `DeskAssist.exe`,
plus `app/` (agent, config, vendored yaml, tools, `sitecustomize.py`).

On the VM the desktop shortcut target is **`runtime\DeskAssist.exe` with no arguments**: the
bundle's `DeskAssist._pth` ends with `import site`, so `app/sitecustomize.py` starts the run during
interpreter start-up and the CommandLine field a judge reads in Sysmon is the bare executable path.
`runtime\DeskAssist.exe -m agent run` (Start in `app`) is the documented fallback. Run length and
objective come from `config/default.yaml`. See `dist/DeskAssist/README_VM.txt`,
`docs/rubric-coverage.md` and `docs/kellyn-changes.md`.

QA tools (stdlib): `tools/timing_analyzer.py` (Procmon CSV gaps, CV, compare with a human capture),
`tools/sysmon_parent_checker.py` (Event Viewer XML/CSV, non-explorer parents), `tools/task_timeline.py`.

## Development commands

- List scenarios: `python -m agent list-objectives`
- Preview one objective without touching a desktop: `python -m agent dry-run --objective web_surfing`
- A full-length run on a virtual clock, scored against the rubric, in about a second:
  `python -m agent simulate --minutes 15 --seed 7`
- Score any action log (simulated or a real one off the VM):
  `python -m agent verify logs/actions.jsonl --report logs/scorecard.md`
- Several seeds at once, non-zero exit on any flagged criterion: `python -m agent selftest --runs 6`
- The judged run, from a shortcut in an unlocked Windows test VM: `python -m agent run`
- Omit `--objective` to choose among scenarios by weight. Add `--seed N` for repeatable development
  runs; leave it out for judged runs, where every run should look different.
- Stop a run cleanly by creating the configured stop file (default `STOP_AGENT.txt` beside `config/`).

Dry runs and `simulate` answer window queries from a simulated Windows desktop driven by the
keystrokes the agent sends (`agent/win/fake_desktop.py`), so startup latency, the certificate
interstitial, dead hosts and misclicks are all exercised off Windows.

To summarize the action log independently, run `python -m reports` or pass a JSONL file path.

## How to add an objective

1. Add a YAML file under `config/objectives/`.
2. Set its `name`, optional `weight` and `params`, and ordered `plan` of skill calls.
3. Reference parameters with `{param}` placeholders. The runner loads objective files at startup.

## How to add a skill

1. Add a class under `agent/skills/` and decorate it with `@register_skill("name")`.
2. Implement `execute(context, args)` using the provided primitives.
3. Add a call to the skill's registered name in an objective YAML plan.

Skills should avoid direct timing calls and must not import PyAutoGUI. Keep test scenarios bounded and use harmless sample data. GUI details may need adjustment for the applications installed in the VM.

## Monitoring notes

- Correlate JSONL run IDs with endpoint telemetry.
- Keep ordinary process lineage visible and document expected events for each objective.
- `tools/sysmon_parent_checker.py` lists process creation events and parent images for review.

## Repository map

Short handoff notes for the files currently in the project:

- `README.md` — desktop app startup, development commands, authoring notes, monitoring notes, and this file map.
- `requirements.txt` — Python packages needed to run and develop the harness.
- `.gitignore` — local environments, generated logs/reports, caches, and build output excluded from Git.
- `agent/__init__.py` — marks `agent` as an importable Python package.
- `agent/__main__.py` — development CLI entry point for listing, previewing, and running objectives.
- `agent/app.py` — composition root that builds runtime components and exposes the desktop entry point.
- `agent/clock.py` — real and virtual time sources, injected so a 15 minute run can be replayed offline.
- `agent/perception.py` — window title and process name to page state (ready, certificate warning, dead host).
- `agent/session.py` — attention Markov chain, tempo drift and fatigue, which scale every pause.
- `agent/report.py` — rubric scorecard from an action log: gap CV and histogram, task timeline, resources.
- `agent/win/desktop.py` — read-only Windows introspection: foreground window, our own CPU and memory.
- `agent/win/fake_desktop.py` — simulated desktop that reacts to the agent's keystrokes, for offline runs.
- `sitecustomize.py` — starts the run when `DeskAssist.exe` is launched with no arguments at all.
- `agent/config.py` — typed settings/objective data and YAML loading helpers.
- `agent/interfaces.py` — interfaces shared by input backends and runtime components.
- `agent/logger.py` — writes action/run events to JSON Lines.
- `agent/registry.py` — registry for named skills.
- `agent/runner.py` — executes objective plans and handles run control.
- `agent/timing.py` — configurable pacing and timing distributions for actions.
- `agent/input/__init__.py` — package marker for input implementations.
- `agent/input/fake_backend.py` — records simulated input for safe dry runs.
- `agent/input/keyboard.py` — keyboard interaction helpers.
- `agent/input/mouse.py` — mouse movement and click helpers.
- `agent/input/pyautogui_backend.py` — desktop input adapter backed by PyAutoGUI.
- `agent/input/scroll.py` — scrolling interaction helpers.
- `agent/objectives/__init__.py` — package marker for objective support code.
- `agent/objectives/yaml_objective.py` — loads and represents YAML-defined objective plans.
- `agent/skills/__init__.py` — imports built-in skills so they register with the skill registry.
- `agent/skills/base.py` — shared skill context and base skill definitions.
- `agent/skills/browser.py` — browser-oriented actions used by objective plans.
- `agent/skills/launch.py` — application launch actions used by objective plans.
- `agent/skills/office.py` — office application actions used by objective plans.
- `config/default.yaml` — default runner, timing, input, and logging settings.
- `config/objectives/web_surfing.yaml` — the primary scenario: open the browser, visit mock sites, read, follow links, close.
- `config/objectives/office_worker.yaml` — office work scenario plan.
- `tests/test_no_banned_calls.py` — guards architectural constraints on skill/input code.
- `tests/test_runner.py` — checks runner behavior and objective execution.
- `tests/test_timing.py` — checks timing and pacing behavior.
- `tests/test_typing.py` — checks keyboard typing behavior.
- `tests/test_perception.py` — window title classification, including Edge's zero-width space.
- `tests/test_launch.py` — launch verification, retry and refusal to type into a window that never opened.
- `tests/test_browser_recovery.py` — certificate interstitial, dead hosts, misclicks.
- `tests/test_session.py` — attention states, fatigue, bounded pause multipliers.
- `tests/test_plan.py` — plan groups, deadline awareness, clean stop.
- `tests/test_simulation.py` — end to end: four 15 minute runs scored against the rubric.
- `tools/sysmon_parent_checker.py` — reviews process creation records and parent images.
- `tools/timing_analyzer.py` — analyzes observed action timing data.
- `logs/README.md` — describes the generated action log and handling of run data.
- `ui/README.md` — scope and usage notes for the operator interface.
- `ui/__main__.py` — local Tkinter operator interface for selecting, starting, and stopping runs.
- `docs/operator-guide.md` — operator setup, execution, stop, and review workflow.
- `docs/scenario-authoring.md` — guidance for adding bounded, auditable scenarios.
- `docs/team-handoff.md` — detailed implemented/not-yet-implemented status and teammate file map.
- `docs/kellyn-changes.md` — what changed on the `kellyn` branch and why.
- `docs/rubric-coverage.md` — each rubric criterion mapped to the code that implements it and the command that proves it.
- `reports/README.md` — explains where generated run summaries belong and how they are handled.
- `reports/__main__.py` — generates one Markdown summary per run from action JSONL.

## Operator-facing structure

- `ui/` — primary operator interface that calls the existing runner, shows scenario/run status, and exposes start/stop controls.
- `docs/` — handoff and operating documentation.
- `logs/actions.jsonl` — generated per-action records with run IDs; created on the first logged action.
- `reports/` — location for reviewed/exported run summaries; generated reports should include a run ID for telemetry correlation.

The interface and report generation are intentionally small; scenario execution remains in the existing runner.
