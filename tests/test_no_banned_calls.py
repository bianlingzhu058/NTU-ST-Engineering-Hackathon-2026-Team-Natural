"""Guard the runtime package against process-based application control."""
from pathlib import Path
import re


def test_no_process_launch_or_kill_calls():
    root = Path(__file__).parents[1] / "agent"
    banned = re.compile(r"\bsubprocess\b|\bos\s*\.\s*(?:system|startfile)\b|\b(?:Start-Process|pywinauto)\b", re.I)
    hits = [(path, line_no, line) for path in root.rglob("*.py") for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if banned.search(line)]
    assert not hits, "Forbidden app control references: " + repr(hits)
