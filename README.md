# Synthetic Human Agent (Team Natural)

A synthetic desktop user that performs real web and office work on a Windows VM while
looking human in process telemetry (Sysmon / Procmon / Process Explorer). Built for the
NTU × ST Engineering hackathon.

It runs **offline, with no pip and no third-party packages**, using the Python standard
library only (input is driven through `ctypes` + `SendInput`; YAML is parsed by a tiny
built-in parser). Every application is opened the way a person opens it (through the Windows
shell), so each app's parent process is `explorer.exe` and `python.exe` never spawns a child,
opens a socket, or writes a task file.

> **Responsible use.** This is a synthetic-activity tool for **authorized test VMs only**. The
> operator UI requires an explicit "authorized, unlocked test VM" confirmation before it will
> drive the desktop.

## Objectives

| Objective        | App                | What it does |
|------------------|--------------------|--------------|
| `web_surfing`    | Edge Test (Edge)   | Launch, visit sites, scroll & read, hover the nav bar, Ctrl+F find, follow links, sometimes open/close a new tab, close |
| `office_writer`  | OpenOffice Writer  | Open Writer, compose a short note in human "P-bursts", emphasise the title (Heading 1, centred, underlined), save through the Save As dialog, close |
| `office_calc`    | OpenOffice Calc    | Open Calc, enter a table, add a `=SUM()` row, bold the header, save as `.ods`, close |
| `cross_app`      | Edge → Calc        | Browse a site, **copy its URL**, open Calc, enter gathered figures, **paste the source** below the table, then save: a real browser→clipboard→spreadsheet data flow |
| `file_admin`     | File Explorer      | Open Explorer (Win+E), browse a few folders via the address bar, skim them (read-only), natively part of `explorer.exe` |

Run a single objective, a weighted random mix, or **all objectives** in sequence.

Before typing into a freshly-launched app, the agent **confirms the right window is actually in
front** by reading its title through the Win32 accessibility API (`GetForegroundWindow`), never
by screenshots or OCR. This makes launches reliable (no more typing a URL into the Start menu)
without the CPU cost or EDR red flag of screen-capturing.

## How to run on the VM

### Prerequisites (one-time VM setup)

1. **Python 3.12** installed (64-bit). No packages needed, stdlib only.
2. **Edge Test shortcut** (for `web_surfing`): a desktop shortcut named **"Edge Test"** whose
   target is
   `msedge.exe --ignore-certificate-errors --user-data-dir=C:\EdgeTest`
   (the separate profile is what makes the cert flag apply, so the organisers' mock sites
   load real content). Copy that shortcut into the Start-menu programs folder so Windows
   search resolves it:
   ```cmd
   copy "%USERPROFILE%\Desktop\Edge Test.lnk" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Edge Test.lnk"
   ```
   Confirm: press **Win**, type `Edge Test`, and the Best Match must be **Edge Test**.
3. **OpenOffice** installed (for `office_writer` / `office_calc`). The agent launches Writer
   and Calc via `swriter` / `scalc`.

### Launching the agent (DeskAssist shortcut, recommended for scoring)

Starting `python -m ui` from a terminal makes the agent process a child of `cmd.exe` /
`powershell.exe`, a visible automation artifact in the logs. To give the agent its own
`explorer.exe` parent (the same lineage as the apps it opens), start it from a desktop shortcut:

1. Make a console-less copy of the launcher (a renamed `pythonw.exe`):
   ```cmd
   copy "C:\Path\To\Python\pythonw.exe" DeskAssist.exe
   ```
2. Create a desktop shortcut whose target is `"<agent folder>\DeskAssist.exe" -m ui` and whose
   **Start in** is the agent folder.
3. **Double-click the shortcut.** It opens the operator UI (below), and in Process Explorer
   `DeskAssist.exe` now shows parent `explorer.exe`, as do `msedge.exe` / `soffice.bin`.

For development you can instead launch straight from a terminal (the terminal becomes the parent):

```cmd
cd <folder containing agent\, config\, ui\>
python -m ui
```

### Operator UI

In the **Synthetic Activity Harness** window:
1. **Scenario** → `all objectives`, `web_surfing`, `office_writer`, `office_calc`, `file_admin`, or `cross_app`
2. **Duration** → minutes (e.g. 15 for a full session; about 8 min fits one full "all objectives" cycle)
3. **Uncheck** ☐ *Dry run (no desktop input)*  ← required to actually drive the desktop
4. **Check** ☑ *I confirm this is an authorized, unlocked test VM*
5. **Start run** (or **Ctrl+Alt+F9**). **Stop run** / **Ctrl+Alt+F10** halts within about 0.3 s.

Keep the VM **unlocked** during a run, since the agent is driving the real keyboard and mouse.

### Command line (no UI)

```cmd
python -m agent run --objective web_surfing --minutes 3     # one objective
python -m agent run --objective all --minutes 15            # all objectives, fixed order
python -m agent run --minutes 15                            # weighted random mix
```

A CLI run logs to `logs\agent.log` (so the terminal looks idle while it works). Stop it with
**Ctrl+C**, or create the stop file `STOP_AGENT.txt` next to the `config` folder.

## What makes it look human (grounded in research)

- **Session timing.** Gaps between tasks use a heavy-tailed mixture (coefficient of variation
  about 1.55, the human band from Barabási 2005 / Goh & Barabási 2008), not a near-uniform
  schedule that reads as a bot.
- **Writing.** Documents are composed in roughly 8 to 9 word bursts, with think-pauses between
  them and longer pauses at paragraphs (Chenoweth & Hayes 2001; Conijn 2019).
- **Data entry.** Spreadsheet cells are keyed at a visible ~10-key pace with irregular
  between-cell pauses, not pasted instantly.
- **Session fatigue.** Every pause lengthens slowly over the session (1.0 → about 1.12 over
  about 20 min), the way a person tires: a subtle drift across the whole timeline. Set
  `timing.fatigue.max: 0` to disable.
- **Cross-application work.** The `cross_app` objective moves a real value (a page URL) from the
  browser into a spreadsheet via the clipboard, the kind of multi-app action a single-app bot
  cannot fake (Action Complexity).
- **Window-aware launches.** Reads the foreground window title (accessibility API, not pixels)
  to confirm the right app is up before acting, giving reliability without "seeing" the screen.
- **Navigation.** URLs typed exactly (no auto-corrupting typos); links followed and tabs
  opened/closed as a person browsing would.
- **Process authenticity.** Apps launched through the shell → parent is `explorer.exe`; files
  written by `soffice.bin` through its own Save As dialog; `python.exe` stays childless,
  offline, and silent on disk.
- **Silent on disk during the run.** The action log is **buffered in memory** and written once
  at the end (`logging.mode: buffered`), so `python.exe` emits no steady stream of `WriteFile`
  events while it works, keeping the timeline the judges filter to the agent clean. Set
  `logging.mode: off` for zero disk, or `append` for live logs in development.

## References

The timing and writing models are grounded in published human-behaviour research:

- Barabási, A.-L. (2005). The origin of bursts and heavy tails in human dynamics. *Nature*, 435(7039), 207-211.
- Goh, K.-I., & Barabási, A.-L. (2008). Burstiness and memory in complex systems. *EPL (Europhysics Letters)*, 81(4), 48002.
- Chenoweth, N. A., & Hayes, J. R. (2001). Fluency in writing: Generating text in L1 and L2. *Written Communication*, 18(1), 80-98.
- Conijn, R., Roeser, J., & van Zaanen, M. (2019). Understanding the keystroke log: the effect of writing task on keystroke features. *Reading and Writing*, 32(9), 2353-2374.

## How this maps to the judging criteria

| Criterion | Weight | How the agent addresses it |
|---|---|---|
| Process Telemetry Authenticity | 30% | Apps (and the agent itself, via DeskAssist) are launched through the shell, so the parent is `explorer.exe`; no `cmd`/`powershell` launch, no scripting flags (`-ExecutionPolicy Bypass`, `-EncodedCommand`); `python.exe` spawns no children |
| Human Entropy & Timing | 30% | Lognormal per-action pauses plus a heavy-tailed between-task mixture (measured CV about 1.3, well above the 0.4 target), occasional multi-second reading pauses, and session fatigue drift |
| Action Complexity | 20% | Five objectives, including a real browser-to-clipboard-to-spreadsheet flow (`cross_app`), title formatting in Writer, and a `=SUM()` table in Calc |
| Resource Efficiency | 20% | No screenshots or OCR; the window sensor reads only the foreground title; the pacer uses real sleeps (no busy-wait); the action log is buffered and written once at the end |

## Verifying authenticity

1. On the VM, start **Sysmon**, **Process Monitor** (filter Operation is `Process Create`), and
   **Process Explorer** (add the **Parent PID** column).
2. Launch the agent from the **DeskAssist shortcut** and run `all objectives`.
3. Confirm every `msedge.exe` / `soffice.bin` / `swriter.exe` / `scalc.exe`, and `DeskAssist.exe`
   itself, has **parent `explorer.exe`**, and that no command line carries a scripting flag.
4. `python tools\sysmon_parent_checker.py <sysmon export>` flags anything whose parent is not
   `explorer.exe`.

## Key config knobs

In `config/default.yaml`:
- `timing.fatigue.max`  how much pauses lengthen over a session (set `0` to disable).
- `logging.mode`  `buffered` (default, silent on disk during the run), `off`, or `append`.
- `typing.typo_rate`  per-letter chance of a corrected typo in prose (never in URLs or filenames).

In `config/objectives/web_surfing.yaml`:
- `showcase_site`  the first site each run visits (pinned for a demo); set to `"{sites}"` for a fully random first site.

## Notes & environment specifics

A few behaviours that are specific to the organisers' test VM or are deliberate design choices:

- **Certificate flag (expected on the mock VM).** The organisers' mock sites use TLS certificates
  that have expired, so Edge is launched through the **"Edge Test"** profile with
  `--ignore-certificate-errors`. This is only to load the mock content; on a machine with valid
  certificates the flag is not needed.
- **Sampled content.** Document and table content is chosen at random from a fixed set, so the
  same content can recur across a long session.
- **Content-blind reading pauses.** Reading pauses are scheduled without inspecting page content,
  so a pause may occasionally land on an empty area of a page.

## Development & verification

```cmd
python -m agent list-objectives                 # list the objectives
python -m agent dry-run --objective web_surfing # simulate without touching the desktop
python -m pytest -q                             # 38 unit tests (timing shape, window sensor, buffered logging, no-banned-calls, etc.)
```

**Analysis & evidence tools** (stdlib, for the report/demo):
```cmd
python tools\timing_validate.py                       # proves the gap model sits in the human band (CV / burstiness / memory)
python tools\resource_monitor.py --name DeskAssist.exe --duration 180 --csv usage.csv  # CPU% / RAM footprint during a run (VM only)
python tools\task_timeline.py logs\actions.jsonl      # per-task timeline (task, start, end, duration, actions)
python tools\timing_analyzer.py logs\actions.jsonl    # inter-burst gap CV / burstiness from a real capture
python tools\sysmon_parent_checker.py <export>        # flags any process whose parent is not explorer.exe
```

## Project layout

```
agent/            runtime: runner, timing, config, logging, registry
  input/          stdlib SendInput backend (VM) + fake backend (dry runs) + win_state (window sensor) + optional pyautogui (dev)
  skills/         launch, browser, office, clipboard, explorer: the actions objective plans call
  objectives/     loads YAML objective plans
  mini_yaml.py    tiny stdlib YAML parser (so the VM needs no PyYAML)
config/
  default.yaml    timing distributions (incl. fatigue), input backend, runner/logging (buffered) settings
  objectives/     web_surfing, office_writer, office_calc, file_admin, cross_app (.yaml)
ui/               Tkinter operator window (scenario, duration, start/stop)
tools/            timing_validate, resource_monitor, task_timeline, timing_analyzer, sysmon_parent_checker
tests/            38 unit tests
```

## Adding an objective

1. Add a YAML file under `config/objectives/` with a `name`, optional `weight`/`params`, and an
   ordered `plan` of skill calls (reference params with `{name}` placeholders; `chance:` gates a
   step probabilistically).
2. If it needs a new action, add a class under `agent/skills/`, decorate it with
   `@register_skill("name")`, implement `execute(context, args)`, and call that name in the plan.
   Skills use the injected primitives and never call timing or input APIs directly.
