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

---

# Second pass, 10 Oct 2026 evening: version 0.3-web

Written against the rubric line by line. The mapping of criterion to code to proof is in
`docs/rubric-coverage.md`. Summary of what is new:

## The agent now sees the screen (new)
- `agent/win/desktop.py`: foreground window title, foreground process image name, and our own
  CPU and memory counters, through user32/kernel32 ctypes. Read-only, wrapped so an API failure
  never ends a run. No process is ever created or enumerated.
- `agent/perception.py`: title to page state (ready, privacy_error, unreachable, new_tab,
  absent). Normalises Edge's zero-width space. Process name wins over title when available.
- Why: the organisers' mock-site certificates expired on 9 Jul 2026, so every navigation lands
  on "Your connection isn't private". The old open-loop code typed the next URL into that page.
- `config/default.yaml` has `perception.enabled` to fall back to open-loop on the day.

## Launches are verified, not assumed
- `open_app` polls until the expected window is in front, retries a second strategy, and raises
  instead of typing blind. `Win+R` default weight is now zero (RunMRU is a tell).
- `close_app` confirms the window is gone, pressing Ctrl+W only while the browser is still there.
- Three consecutive actions with no expected window raise `AbortRun` and end the run.
- Office skills check Word is in front before typing a paragraph into whatever has focus.

## Recovery behaviour the mock sites need
- `go_to_url`: new tab sometimes, bare host or full URL, then classify what came up. Certificate
  warning is cleared (Advanced then Continue, state re-read between the two Enters, then the
  keyboard bypass phrase as fallback). Dead host leads to Alt+Left and another site.
- `follow_link`: F6 into the page rather than Tab from the address bar, which used to walk Edge's
  own toolbar. A Tab+Enter that changed nothing is logged `no_change`, not retried.
- `reload_page`, `close_tab`, `dismiss_interstitial` added. `scroll_and_read` and `find_on_page`
  skip error pages and use Page Down or End sometimes.

## Timing: a curve, not a flat random band
- `agent/session.py`: four-state attention Markov chain times a drifting tempo times mild
  fatigue, multiplying every pause. Written on every action line (`attention`, `pause_scale`).
- `agent/timing.py`: per-kind `max_seconds` caps so one long draw cannot eat the budget.
- `agent/clock.py`: `RealClock` and `VirtualClock`, injected everywhere.

## Proving it offline
- `agent/win/fake_desktop.py`: a simulated Windows desktop driven by the keystrokes the agent
  sends, so dry runs exercise startup latency, the interstitial, dead hosts and misclicks.
- `agent simulate --minutes 15`: a full run on the virtual clock, instantly, on Linux.
- `agent verify <log>`: rubric scorecard (per-criterion verdict, gap CV and histogram, task
  timeline, resource numbers) from a simulated or a real log. `agent/report.py`.
- `agent selftest --runs 6`: simulate and score several seeds, non-zero exit on any flag.
- Tests went from 19 to 61: perception, launch verification and failure, interstitial recovery,
  dead links, session model, plan groups, and nine end-to-end assertions on four 15 minute runs.

## Plans
- `config/objectives/web_surfing.yaml` uses a `group:` block repeated 3 to 6 times (one site
  visit per iteration), with `min_time_left` so the closing step always runs before the deadline.
- The runner will not start a task that cannot finish inside the remaining budget.

## Packaging: no arguments in the command line
- `sitecustomize.py` plus `DeskAssist._pth` ending in `import site` means the shortcut target is
  just `DeskAssist.exe`, so Sysmon's CommandLine field is the bare path. `-m agent run` still
  works as a documented fallback.
- `packaging/build_bundle.sh` now accepts either a python.org embeddable zip or a previously
  built `DeskAssist.zip` (it reuses the runtime), and writes both `._pth` names.
