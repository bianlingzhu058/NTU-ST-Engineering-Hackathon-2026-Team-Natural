"""Guard the runtime package: no process control, no screenshots, no fixed sleeps, no third-party imports.

These four tests are the Process Telemetry and Resource Efficiency criteria expressed as code.
If a process API ever reaches the agent package, the apps it opens stop being children of
explorer.exe; if a screen-capture API reaches it, CPU stops looking like one idle user.
"""
from pathlib import Path
import re

ROOT = Path(__file__).parents[1] / "agent"
STDLIB_OK = {"abc", "argparse", "collections", "ctypes", "dataclasses", "datetime", "json", "logging", "math",
             "os", "pathlib", "random", "re", "sys", "threading", "time", "typing", "uuid", "urllib", "__future__"}
SLEEP_ALLOWED = {"timing.py", "clock.py"}


def _lines():
    for path in ROOT.rglob("*.py"):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            yield path, line_no, line


def test_no_process_launch_or_kill_calls():
    banned = re.compile(r"\bsubprocess\b|\bos\s*\.\s*(?:system|startfile|kill|exec\w*|spawn\w*|popen)\b"
                        r"|\b(?:Start-Process|pywinauto|taskkill|CreateProcess\w*|ShellExecute\w*|WinExec"
                        r"|EnumProcesses|CreateToolhelp32Snapshot)\b", re.I)
    hits = [(p.name, n, l.strip()) for p, n, l in _lines() if banned.search(l)]
    assert not hits, "Forbidden process control references: " + repr(hits)


def test_no_screen_capture():
    """Screenshot scanning is the classic way to lose the 20% resource criterion."""
    banned = re.compile(r"\b(?:screenshot|locateOnScreen|ImageGrab|pyscreeze|BitBlt|PrintWindow|mss)\b", re.I)
    hits = [(p.name, n, l.strip()) for p, n, l in _lines() if banned.search(l)]
    assert not hits, "Screen capture in the agent: " + repr(hits)


def test_no_fixed_sleeps_outside_the_clock_and_timing_modules():
    hits = [(p.name, n, l.strip()) for p, n, l in _lines()
            if re.search(r"\btime\.sleep\(", l) and p.name not in SLEEP_ALLOWED]
    assert not hits, "time.sleep outside the pacing modules: " + repr(hits)


def test_only_stdlib_imports_in_agent_package():
    """The VM runtime is the Python embeddable zip with no pip: stdlib, vendored yaml, optional pyautogui."""
    allowed = STDLIB_OK | {"yaml", "pyautogui"}
    bad = []
    for path, line_no, line in _lines():
        match = re.match(r"\s*(?:from|import)\s+([A-Za-z_][\w]*)", line)
        if match and not line.lstrip().startswith(("from .", "import .")) \
                and match.group(1) not in allowed and match.group(1) != "agent":
            bad.append((path.name, line_no, line.strip()))
    assert not bad, "Non-stdlib import in agent/: " + repr(bad)


def test_pyautogui_only_in_its_backend():
    hits = [(p.name, n) for p, n, l in _lines() if "pyautogui" in l and p.name not in ("pyautogui_backend.py", "app.py")]
    assert not hits, repr(hits)


def test_every_launch_strategy_goes_through_the_windows_shell():
    """Each strategy is a keystroke to explorer.exe, which is what makes the parent explorer.exe."""
    from agent.skills.launch import STRATEGIES
    source = (ROOT / "skills" / "launch.py").read_text(encoding="utf-8")
    assert set(STRATEGIES) == {"taskbar", "start_search", "run_dialog"}
    for key in ('combo("win"', 'press("win")'):
        assert key in source


def test_no_untagged_numbers_in_behaviour_code():
    """Every behaviour number lives in behaviour/params.py with a source and a confidence tag.

    In the skills and input models, a sleep or random draw may not take a bare numeric literal;
    it must read the value with P("name"). This keeps guesses visible instead of hidden in code.
    """
    pattern = re.compile(r"\b(?:uniform|randint|tiny|sleep|lognormvariate|gauss)\(\s*-?\d")
    hits = []
    for folder in ("skills", "input"):
        for path in (ROOT / folder).glob("*.py"):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                zero_centred = re.search(r"\(\s*0(?:\.0)?\s*,", line)  # noise around zero is structure, not a value
                if pattern.search(line) and not zero_centred and "# not behaviour" not in line:
                    hits.append((path.name, n, line.strip()))
    assert not hits, "numeric literal in a behaviour draw, move it to params.py: " + repr(hits)
