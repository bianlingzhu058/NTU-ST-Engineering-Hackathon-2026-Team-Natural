# Synthetic Desktop Activity Harness

- Runs labeled desktop scenarios in an authorized test VM.
- Writes synthetic run and action records to `logs/actions.jsonl` for monitoring validation.
- Uses a fake input backend for dry runs; Windows desktop runs use PyAutoGUI.

## How to run the code

1. Install Python 3.11 or newer.
2. From the project folder, install dependencies:

   ```sh
   pip install -r requirements.txt
   ```

3. List the available objectives:

   ```sh
   python -m agent list-objectives
   ```

4. Preview one objective without controlling the desktop:

   ```sh
   python -m agent dry-run --objective research_topic
   ```

5. On Windows, run an objective in an unlocked test VM:

   ```sh
   python -m agent run --objective research_topic --minutes 15
   ```

   Omit `--objective` to choose among objectives by weight. Add `--seed N` for repeatable development runs.

6. Stop a running session by creating the configured stop file (default: `.agent-stop`). Review the recorded actions in `logs/actions.jsonl`.

The CLI is for development. `agent.app.run_desktop()` is the entry point to package behind a double-click launcher.

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

- `README.md` — setup, CLI workflow, authoring notes, monitoring notes, and this file map.
- `requirements.txt` — Python packages needed to run and develop the harness.
- `.gitignore` — local environments, generated logs/reports, caches, and build output excluded from Git.
- `agent/__init__.py` — marks `agent` as an importable Python package.
- `agent/__main__.py` — CLI entry point for listing, previewing, and running objectives.
- `agent/app.py` — composition root that builds runtime components and exposes the desktop entry point.
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
- `config/objectives/idle_browse.yaml` — bounded idle browsing scenario plan.
- `config/objectives/office_worker.yaml` — office work scenario plan.
- `config/objectives/research_topic.yaml` — research browsing scenario plan.
- `tests/test_no_banned_calls.py` — guards architectural constraints on skill/input code.
- `tests/test_runner.py` — checks runner behavior and objective execution.
- `tests/test_timing.py` — checks timing and pacing behavior.
- `tests/test_typing.py` — checks keyboard typing behavior.
- `tools/sysmon_parent_checker.py` — reviews process creation records and parent images.
- `tools/timing_analyzer.py` — analyzes observed action timing data.
- `ui/README.md` — scope and intended responsibilities for the future operator interface.
- `docs/operator-guide.md` — operator setup, execution, stop, and review workflow.
- `docs/scenario-authoring.md` — guidance for adding bounded, auditable scenarios.
- `reports/README.md` — explains where generated run summaries belong and how they are handled.

## Planned operator-facing structure

- `ui/` — thin operator interface that will call the existing runner, show scenario/run status, and expose start/stop controls.
- `docs/` — handoff and operating documentation.
- `reports/` — location for reviewed/exported run summaries; generated reports should include a run ID for telemetry correlation.

The UI and report generation are not implemented yet; these folders establish ownership and documentation boundaries without duplicating the runner.
