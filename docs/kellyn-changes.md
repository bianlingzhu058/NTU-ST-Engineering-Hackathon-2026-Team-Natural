# Changes on the `kellyn` branch (10 Oct 2026)

Built on Lin's scaffold. Layout, interfaces, registry, YAML objectives and the
template-method skill all kept. What changed and why:

## Runtime: no pip on the VM
- `agent/input/sendinput_backend.py` (new): keyboard and mouse through user32
  `SendInput` via `ctypes`. Standard library only. Chosen by `input.backend:
  sendinput` in `config/default.yaml`. `pyautogui_backend.py` stays for laptop
  development (`input.backend: pyautogui`).
- `vendor/yaml/`: pure-Python PyYAML, used automatically when `import yaml` fails.
- `packaging/build_bundle.sh`: makes `dist/DeskAssist.zip` = Python embeddable
  runtime (pythonw.exe copied to DeskAssist.exe) + app folder. Runs on the VM
  from a desktop shortcut, parent explorer.exe, nothing installed.
- `tests/test_no_banned_calls.py` now also fails on any non-stdlib import in
  `agent/` and on `time.sleep` outside `timing.py`.

## Timing: nothing uniform
- Every pause kind (`micro`, `step`, `read`, `think`, `gap`) is lognormal
  with optional long pauses, configured by median and sigma. Previously
  `micro`/`step`/`read` were uniform ranges.
- `tests/test_timing.py` asserts CV > 0.4 for every kind.
- Runner waits a `gap` (median 14 s) between tasks, not a `step`.

## Logging: one write per action
- `BaseSkill.run` writes one JSONL line per skill, after it finishes (was two:
  start and end). Judges filter Procmon to the agent process, so these
  writes are the timeline they measure. Runner logs `task_start`/`task_end`
  with duration: that is the task timeline the mentor asked to see
  (`tools/task_timeline.py` renders it).

## Skills
- `open_app`: random launch route per call: `Win+<slot>` (taskbar), Start
  search, `Win+R`. All have explorer.exe as parent.
- `close_app`: `method: ctrl_w` repeats Ctrl+W (never the close-all-tabs
  dialog) or `alt_f4`.
- `follow_link` (new): Ctrl+L, Esc, click page body, Tab n times, Enter,
  sometimes Alt+Left. `go_back` (new).
- `go_to_url`/`search`/`find_on_page`: a list value is sampled at random.
- `scroll_and_read`: random burst count, idle mouse drift.
- `type_document`: title + paragraphs with think pauses. `save_file`: Ctrl+S,
  filename with `{n}` random number, Enter (Word, WordPad, Notepad).
- Typing: QWERTY-neighbour typos, sometimes noticed one key late.
- Mouse: Bezier from the current position, overshoot and correction, clamped
  40 px from screen corners.

## Objectives
- `web_surfing.yaml` (replaces idle_browse and research_topic): mock-site
  list from the technical guide, random count of sites, optional link follow.
- `office_worker.yaml`: Word on taskbar slot 2, three ASCII note variants,
  random filenames. Notepad removed (Store app on Win11: parent svchost.exe).
- Plan steps support `chance:` and `repeat: [min, max]`; a `step` pause is
  taken between plan steps.

## Tools (stdlib)
- `tools/timing_analyzer.py`: Procmon CSV or JSONL, burst clustering, CV,
  percentiles, histogram, near-uniform warning, `--compare` with KS distance,
  `--report` Markdown.
- `tools/sysmon_parent_checker.py`: Event Viewer XML or CSV export, flags
  non-explorer parents and scripting flags, `--image` filter.
- `tools/task_timeline.py`: task table from `actions.jsonl`.

## Known limits
- `ui/` (Tkinter) does not run on the embeddable runtime (no tkinter there).
  The judged run uses the shortcut, not the UI.
- The agent process on the VM is a renamed `pythonw.exe` with `-m agent run`
  in its command line. A PyInstaller build removes that; optional.
