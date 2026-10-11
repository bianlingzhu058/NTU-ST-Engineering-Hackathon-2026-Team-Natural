# DeskAssist v1.0-research: design notes for the team

Branch `v1-research` (from `kellyn`). Written 11 Oct 2026. Read this before changing behaviour code.

## What changed from 0.3-web and why

0.3-web worked mechanically on VM 1061 but its behaviour numbers were hand-picked. The first real
runs showed the cost: a pause of up to 25 s after every "." (even inside `www.apple.com`), the
browser assumed to be Edge (whose expired-certificate page has no way through), links followed by
pressing Tab a random number of times, and a "mood" multiplier that made gaps follow patterns.

v1 keeps the plumbing that was proven on the VM and rebuilds the behaviour from research:

| Kept (proven on the VM) | Rebuilt from research |
|---|---|
| SendInput keyboard/mouse driver (now with separate down/up events) | Typing: lognormal key intervals, holds, rollover, errors and corrections |
| Launching apps only through the Windows shell (explorer.exe parent) | Mouse: Fitts's law timing, submovements, curved paths, click holds |
| Window title/process detection | Scrolling and reading: depth and dwell from eye-tracking and analytics studies |
| `sitecustomize.py` autorun, so the shortcut has no arguments | Browsing: Weibull page dwell, measured navigation mix, mouse clicks on links |
| One log line per macro action, never on a timer | Session: gap mixture with CV 1 to 2, resumption lag, priority-queue task order |

New: Chrome only, UI Automation (link and button positions, stdlib ctypes), OpenOffice Writer and
Calc tasks, Lin's Ctrl+Alt+F10 stop hotkey, a one-paste VM update.

## Where every number lives

`agent/behaviour/params.py`. Every value has a source and a confidence tag:

- **H** verified in the primary paper, **M** solid but adapted or secondary
- **L** our own calculation from a public dataset (CMU keystrokes, Balabit mouse)
- **D** design guess (no published measurement exists), **U** unverified

`python -m agent params` prints the whole table for the write-up; `--guesses` prints only D and U.
`tests/test_no_banned_calls.py` fails if a skill or input file hides a number in a sleep or random
draw instead of reading it from the table. Full citations: `../docs/behaviour-model.md` (project
root) and `../research_notes/`.

## The timing target changed

0.3 aimed for "coefficient of variation of gaps above 0.4". Random (Poisson) timing already has
CV 1, so 0.4 is more regular than random: bot-like. Human activity logs sit at CV 1.6 to 2.2 with
almost no correlation between consecutive gaps (Barabasi 2005, Goh and Barabasi 2008). The
scorecard (`agent verify`) now checks CV 1 to 2, burstiness B 0 to 0.33, and lag-1 memory within
chance. Eight simulated 15-minute sessions all pass (CV 1.03 to 1.44, B 0.01 to 0.17).

## Layout

```
agent/behaviour/params.py   every behaviour number with its source and tag
agent/behaviour/persona.py  one simulated person per run (typing speed, mouse throughput, ...)
agent/behaviour/dist.py     samplers: lognormal, Weibull, truncated Pareto, gap statistics
agent/timing.py             KLM pauses, resumption lag, between-burst gaps, sliced sleep
agent/input/keyboard.py     typing model: plan errors, time keys, play down/up events
agent/input/mouse.py        Fitts movement, submovements, click hold, idle cursor while reading
agent/input/scroll.py       reading a page: depth, dwell per screen, wheel bursts
agent/win/uia.py            UI Automation client (links and buttons with screen rectangles)
agent/skills/browser.py     go_to_site, navigate, read_page, certificate warning, dead links
agent/skills/office.py      compose_document (Writer), fill_sheet (Calc), save_document
agent/skills/launch.py      open_app / close_app through the shell, OpenOffice Start Center
config/objectives/*.yaml    the three tasks: web_surfing, office_writer, office_calc
```

## Commands

```
python3 -m pytest tests -q                       # 39 tests, includes four full simulated sessions
python3 -m agent simulate --minutes 15 --seed 3  # one session on a virtual clock, then the scorecard
python3 -m agent dry-run --objective office_calc # one task, prints each action
python3 -m agent params --guesses                # the values that are still design guesses
python3 packaging/build_update.py OUT [--minutes 5 --objective web_surfing]   # one-paste VM update
```

On the VM, in a console (python.exe, not DeskAssist.exe):

```
cd C:\DeskAssist\app
..\runtime\python.exe -m agent probe        # switch to Chrome within 5 s; prints what UIA sees
..\runtime\python.exe -m agent verify logs\actions.jsonl
```

## Not yet proven on the VM

1. UI Automation through raw COM vtables (untested on Windows). If `probe` shows no links, set
   `uia: enabled: false`; the agent falls back to find-on-page and the bypass phrase.
2. Start search names "openoffice writer" / "openoffice calc"; the Start Center fallback.
3. Pixels per wheel notch in Chrome (assumed 100).
4. Writer word completion: Enter can accept a suggestion. Paragraphs end with "." so no word is in
   progress, but watch the title line.
5. Whether Calc's Enter after a row of Tabs returns to column A in AOO 4.1.16 (documented for
   LibreOffice).
