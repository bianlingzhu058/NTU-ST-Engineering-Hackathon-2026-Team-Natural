# Rubric coverage: criterion, mechanism, proof

Every row names the code that implements it and the command or export that proves it. Written
10 Oct 2026 for agent version `0.3-web`. Weights are from `docs/scoring-rubric.md`.

Run these three commands to reproduce every number below, offline, with no VM:

```
python3 -m pytest tests -q                              # 61 tests
python3 -m agent simulate --minutes 15 --seed 7          # a full run on a virtual clock
python3 -m agent selftest --runs 6 --minutes 15          # six runs, each scored
```

---

## 1. Process Telemetry Authenticity, 30%

> "Execution chain of tools is not spawn from scripts and are viewed as what is seen when
> executed by an individual in Sysmon or Windows Event Logs."

| What the judges read | What we do | Where |
| --- | --- | --- |
| `ParentImage` of `msedge.exe` in Sysmon Event ID 1 | Applications are opened only by keystrokes to the Windows shell: `Win+<slot>` on a pinned taskbar icon, or `Win`, type the name, `Enter`. The shell starts the app, so the parent is genuinely `explorer.exe`. No code path can start a process. | `agent/skills/launch.py` |
| `CommandLine` of the agent itself | The bundle's shortcut target is `DeskAssist.exe` with **no arguments**. `DeskAssist._pth` ends with `import site`, so `app/sitecustomize.py` starts the run during interpreter start-up. The command line a judge reads is the bare executable path. | `sitecustomize.py`, `packaging/build_bundle.sh` |
| Unexpected child processes | There are none. The agent has no `subprocess`, no `os.system`, no `ShellExecute`, no `CreateProcess`, and the guard test fails the build if one appears. | `tests/test_no_banned_calls.py` |
| A tool that opened something it never checked | Each launch is verified: after sending the keystrokes the agent polls the foreground window until the expected process is in front, retries a second strategy if it is not, and raises rather than typing into whatever has focus. | `agent/skills/launch.py`, `agent/win/desktop.py` |
| Our own introspection showing up as noise | Resolving a window to its process needs `OpenProcess`, which a verbose Sysmon config logs as Event ID 10 (ProcessAccess). Doing that per poll would look like reconnaissance, so the result is cached per window handle: a handful of lookups per run. `perception.use_process_lookup: false` uses titles alone and issues none. | `agent/win/desktop.py` |

`Win+R` exists as a third strategy but its default weight is zero: it writes to the `RunMRU`
registry key and few office workers use it. `tests/test_launch.py` asserts it is never chosen
while another strategy is available.

**Honest limitation.** On the embeddable-runtime bundle the process is `pythonw.exe` copied to
`DeskAssist.exe`, so its PE version resource still says Python. The parent and the command line
are clean; the file description is not. A PyInstaller onedir build with a version resource
removes that, and the write-up should say which one actually ran.

**Proof on the VM:** `python tools/sysmon_parent_checker.py sysmon_final.xml --image msedge.exe
--image DeskAssist.exe`, which flags any non-`explorer.exe` parent and any scripting flag in a
command line, and exits non-zero if it finds one.

---

## 2. Human Entropy and Timing, 30%

> "Are the actions too fast and delays between each action static, or do they follow a realistic
> curve?"

Three layers, because a single random distribution still produces a flat, stationary timeline:

1. **Distribution.** Every pause is drawn from a lognormal (configured by median and sigma) with
   a small probability of a much longer pause mixed in, and a hard cap so one draw cannot eat the
   budget. Five kinds: `micro` between keystrokes, `step` between UI actions, `read` after a page
   loads, `think` before starting something, `gap` between tasks. `agent/timing.py`.
2. **Attention.** A four-state Markov chain (focused, steady, reading, distracted) multiplies
   every pause by 0.65 to 3.1, with a slow random walk on tempo inside each state and mild
   fatigue across the run. So the pace at minute 14 differs from minute 1. `agent/session.py`.
   The state is written on every action line, so the curve is visible in the log.
3. **Structure.** The number of sites per task, their order, the number of scroll bursts, whether
   a link is followed, whether a new tab is used, and whether the URL is typed in full or as a
   bare host are all drawn per run. Two runs never have the same shape.

What the judges actually measure for our process is the gap between our log writes, one per
macro action, written and closed immediately, never buffered and never on a timer. That is why
resource counters ride along on the action line instead of being sampled periodically: a
periodic sampler would put a metronome into the trace being scored.

Measured over six simulated 15 minute runs (`agent selftest --runs 6`):

| seed | tasks | actions | CV | median gap | p95 gap | over 2 s |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 3 | 43 | 0.88 | 16.4 s | 42.5 s | 100% |
| 2 | 5 | 73 | 0.73 | 9.9 s | 29.6 s | 89% |
| 3 | 3 | 46 | 1.09 | 16.1 s | 62.1 s | 93% |
| 4 | 3 | 45 | 1.23 | 13.0 s | 42.8 s | 95% |
| 5 | 2 | 42 | 0.96 | 12.8 s | 66.4 s | 98% |
| 6 | 5 | 54 | 0.70 | 14.1 s | 29.2 s | 96% |

Target is a coefficient of variation above 0.4. The tests enforce it twice: per distribution in
`tests/test_timing.py`, and end to end on the action timeline in `tests/test_simulation.py`,
which also fails on a metronome pattern (more than 30% of gaps within 10% of the commonest
value) and on an absence of reading pauses.

**Proof on the VM:** `python tools/timing_analyzer.py bot_final.csv --process DeskAssist.exe
--compare human_kellyn_1.csv`, which clusters Procmon events into bursts and reports CV,
percentiles, a histogram and a KS distance against a human capture.

---

## 3. Resource Efficiency, 20%

| Risk the rubric names | What we do | Where |
| --- | --- | --- |
| Sustained CPU | The agent sleeps between actions in short interruptible slices and does no polling loop that is not bounded. No screenshots, no image matching, no OCR: a guard test fails the build if a capture API appears. | `agent/timing.py`, `tests/test_no_banned_calls.py` |
| Memory leak or flat line | Nothing accumulates across actions: no screenshot buffers, no growing page cache. Simulated runs stay between 12 and 26 MB working set. The browser is what grows and releases memory, which is the behaviour the rubric describes, so the Process Explorer screenshot must include `msedge.exe` columns, not only the agent. | `agent/report.py` |
| Nobody measuring it | `GetProcessTimes` and `GetProcessMemoryInfo` are read through ctypes and stamped onto every action line (`cpu_seconds`, `working_set_mb`, `private_bytes_mb`), so the log itself carries the resource evidence with no extra file writes. | `agent/win/desktop.py`, `agent/skills/base.py` |

Simulated runs report 0.4% of one core. The real number comes from the VM; `agent verify` prints
it from the log and warns above 5% CPU or 100 MB.

**Proof on the VM:** Process Explorer CPU and Private Bytes columns for `DeskAssist.exe` and
`msedge.exe`, plus the Proxmox Summary graph, plus one run captured with Procmon switched off
(Procmon itself costs 10 to 30% CPU and would otherwise sit on the graph).

---

## 4. The unaccounted 20%

Not stated in any organiser material. Two plausible readings, both covered:

- **Scope and behaviour.** The agent reacts to what is actually on screen instead of replaying a
  macro. It recovers from the expired-certificate interstitial, backs out of hosts that do not
  resolve, treats a Tab-and-Enter that hit a button as a human misclick rather than retrying, and
  stops the run outright rather than typing blind if it loses the desktop.
- **Presentation and evidence.** `agent verify` prints a rubric scorecard with a task timeline
  (task, start, end, duration), which is what the mentor asked to be able to see, plus the gap
  histogram and the resource numbers. It runs on a simulated log offline or on a real log from
  the VM, so the same table goes in the README and the slides.

---

## What the mock sites actually do, and why the code cares

Measured in the VM on 10 Oct 2026: the organisers' intermediate CA ("Prod GeniusPi SWWW CA
Intermediate CA") was valid 8 to 9 Jul 2026, so every site on the "clean" list currently lands on
`NET::ERR_CERT_DATE_INVALID` even after `root_ca.crt` is installed. Mirrored pages also link to
real-world hosts that do not resolve inside the VM.

An open-loop macro types the next URL into that interstitial and the run is nonsense in the logs.
So `agent/skills/browser.py` reads the window title, classifies the page
(`agent/perception.py`), and handles each case:

| Page | Agent behaviour |
| --- | --- |
| normal | read it: scroll bursts with reading pauses, sometimes Ctrl+F, sometimes follow a link |
| certificate warning | Advanced, then Continue, reached by Tab and Enter with the state re-read between presses; if that fails, Chromium's keyboard bypass phrase |
| host unreachable | pause, then Alt+Left and move to another site |
| Tab+Enter hit nothing | log `no_change` and carry on, like a misclick |
| wrong window in front | abort the run after three consecutive sightings rather than type blind |

Dry runs and `agent simulate` answer window queries from a simulated desktop
(`agent/win/fake_desktop.py`) that reproduces all of this, with the interstitial on half of all
navigations by default, so the recovery paths are exercised on Linux before anyone touches the VM.
If `perception.enabled` is set to `false` in `config/default.yaml`, the agent falls back to
open-loop behaviour and every outcome is logged as `unverified`.
