"""Guard the runtime package: no process control, no fixed sleeps, no third-party imports."""
from pathlib import Path
import re

ROOT = Path(__file__).parents[1] / "agent"
STDLIB_OK = {"abc", "argparse", "ctypes", "dataclasses", "datetime", "json", "logging", "math", "pathlib", "random", "re",
             "sys", "threading", "time", "typing", "uuid", "__future__", "collections", "difflib", "os", "traceback"}


def _lines():
    for path in ROOT.rglob("*.py"):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            yield path, line_no, line


def test_no_process_launch_or_kill_calls():
    banned = re.compile(r"\bsubprocess\b|\bos\s*\.\s*(?:system|startfile|kill)\b|\b(?:Start-Process|pywinauto|taskkill)\b", re.I)
    hits = [(p.name, n, l) for p, n, l in _lines() if banned.search(l)]
    assert not hits, "Forbidden app control references: " + repr(hits)


def test_no_fixed_sleeps_outside_timing_module():
    hits = [(p.name, n, l) for p, n, l in _lines() if re.search(r"\btime\.sleep\(", l) and p.name != "timing.py"]
    assert not hits, "time.sleep outside timing.py: " + repr(hits)


def test_only_stdlib_imports_in_agent_package():
    """The VM runtime is the Python embeddable zip with no pip: only stdlib, yaml (vendored) and pyautogui (optional) allowed."""
    allowed = STDLIB_OK | {"yaml", "pyautogui"}
    bad = []
    for p, n, l in _lines():
        m = re.match(r"\s*(?:from|import)\s+([A-Za-z_][\w]*)", l)
        if m and not l.lstrip().startswith(("from .", "import .")) and m.group(1) not in allowed and m.group(1) != "agent":
            bad.append((p.name, n, l.strip()))
    assert not bad, "Non-stdlib import in agent/: " + repr(bad)


def test_pyautogui_only_in_its_backend():
    hits = [(p.name, n) for p, n, l in _lines() if "pyautogui" in l and p.name not in ("pyautogui_backend.py", "app.py")]
    assert not hits, repr(hits)
