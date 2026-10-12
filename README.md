# Synthetic Human Agent — Team Natural

A synthetic desktop user that performs real web and office work on a Windows VM while
looking human in process telemetry (Sysmon / Procmon / Process Explorer). Built for the
NTU × ST Engineering hackathon.

It runs **offline, with no pip and no third‑party packages** — the Python standard library
only (input is driven through `ctypes` + `SendInput`; YAML is parsed by a tiny built‑in
parser). Every application is opened the way a person opens it (through the Windows shell),
so each app's parent process is `explorer.exe` and `python.exe` never spawns a child, opens
a socket, or writes a task file.

## Objectives

| Objective        | App                | What it does |
|------------------|--------------------|--------------|
| `web_surfing`    | Edge Test (Edge)   | Launch, visit sites, scroll & read, hover the nav bar, Ctrl+F find, follow links, sometimes open/close a new tab, close |
| `office_writer`  | OpenOffice Writer  | Open Writer, compose a short note in human "P‑bursts", save through the Save As dialog, close |
| `office_calc`    | OpenOffice Calc    | Open Calc, enter a table, add a `=SUM()` row, bold the header, save as `.ods`, close |

Run a single objective, a weighted random mix, or **all objectives** in sequence.

## How to run on the VM

**Prerequisites (one‑time VM setup):**

1. **Python 3.12** installed (64‑bit). No packages needed — stdlib only.
2. **Edge Test shortcut** (for `web_surfing`): a desktop shortcut named **"Edge Test"** whose
   target is
   `msedge.exe --ignore-certificate-errors --user-data-dir=C:\EdgeTest`
   (the separate profile is what makes the cert flag apply, so the organisers' mock sites
   load real content). Copy that shortcut into the Start‑menu programs folder so Windows
   search resolves it:
   ```cmd
   copy "%USERPROFILE%\Desktop\Edge Test.lnk" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Edge Test.lnk"
   ```
   Confirm: press **Win**, type `Edge Test`, and the Best Match must be **Edge Test**.
3. **OpenOffice** installed (for `office_writer` / `office_calc`). The agent launches Writer
   and Calc via `swriter` / `scalc`.

**Run it — operator UI (recommended):**

```cmd
cd <folder containing agent\, config\, ui\>
python -m ui
```

In the **Synthetic Activity Harness** window:
1. **Scenario** → `all objectives`, `web_surfing`, `office_writer`, or `office_calc`
2. **Duration** → minutes (e.g. 15 for a full session; ~8 min fits one full "all objectives" cycle)
3. **Uncheck** ☐ *Dry run (no desktop input)*  ← required to actually drive the desktop
4. **Check** ☑ *I confirm this is an authorized, unlocked test VM*
5. **Start run** (or **Ctrl+Alt+F9**). **Stop run** / **Ctrl+Alt+F10** halts within ~0.3 s.

Keep the VM **unlocked** during a run — the agent is driving the real keyboard and mouse.

**Run it — command line (no UI):**

```cmd
python -m agent run --objective web_surfing --minutes 3     # one objective
python -m agent run --objective all --minutes 15            # all objectives, fixed order
python -m agent run --minutes 15                            # weighted random mix
```

A CLI run logs to `logs\agent.log` (so the terminal looks idle while it works). Stop it with
**Ctrl+C**, or create the stop file `STOP_AGENT.txt` next to the `config` folder.

## What makes it look human (grounded in research)

- **Session timing.** Gaps between tasks use a heavy‑tailed mixture (coefficient of variation
  ≈ 1.55 — the human band from Barabási 2005 / Goh & Barabási 2008), not a near‑uniform
  schedule that reads as a bot.
- **Writing.** Documents are composed in ~8–9 word bursts with think‑pauses between them and
  longer pauses at paragraphs (Chenoweth & Hayes 2001; Conijn 2019).
- **Data entry.** Spreadsheet cells are keyed at a visible ~10‑key pace with irregular
  between‑cell pauses, not pasted instantly.
- **Navigation.** URLs typed exactly (no auto‑corrupting typos); links followed and tabs
  opened/closed as a person browsing would.
- **Process authenticity.** Apps launched through the shell → parent is `explorer.exe`; files
  written by `soffice.bin` through its own Save As dialog; `python.exe` stays childless,
  offline, and silent on disk.

## Development & verification

```cmd
python -m agent list-objectives                 # list the three objectives
python -m agent dry-run --objective web_surfing # simulate without touching the desktop
python -m pytest -q                             # 22 unit tests (timing shape, no-banned-calls, etc.)
```

**Analysis tools** (stdlib, read the action log or a Procmon/Sysmon export):
```cmd
python tools\task_timeline.py logs\actions.jsonl      # per-task timeline (task, start, end, duration, actions)
python tools\timing_analyzer.py logs\actions.jsonl    # inter-burst gap CV / burstiness (human-ness of timing)
python tools\sysmon_parent_checker.py <export>        # flags any process whose parent is not explorer.exe
```

## Project layout

```
agent/            runtime: runner, timing, config, logging, registry
  input/          stdlib SendInput backend (VM) + fake backend (dry runs) + optional pyautogui (dev)
  skills/         launch, browser, office — the actions objective plans call
  objectives/     loads YAML objective plans
  mini_yaml.py    tiny stdlib YAML parser (so the VM needs no PyYAML)
config/
  default.yaml    timing distributions, input backend, runner/logging settings
  objectives/     web_surfing.yaml, office_writer.yaml, office_calc.yaml
ui/               Tkinter operator window (scenario, duration, start/stop)
tools/            task_timeline, timing_analyzer, sysmon_parent_checker
tests/            22 unit tests
```

## Adding an objective

1. Add a YAML file under `config/objectives/` with a `name`, optional `weight`/`params`, and an
   ordered `plan` of skill calls (reference params with `{name}` placeholders; `chance:` gates a
   step probabilistically).
2. If it needs a new action, add a class under `agent/skills/`, decorate it with
   `@register_skill("name")`, implement `execute(context, args)`, and call that name in the plan.
   Skills use the injected primitives and never call timing or input APIs directly.
