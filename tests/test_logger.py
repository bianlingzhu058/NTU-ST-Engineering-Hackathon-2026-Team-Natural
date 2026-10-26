"""Buffered logging keeps python.exe silent on disk during a run (process authenticity)."""
from agent.logger import JsonlActionLogger


def test_buffered_logger_writes_nothing_until_flush(tmp_path):
    p = tmp_path / "actions.jsonl"
    log = JsonlActionLogger(p, mode="buffered")
    log.log({"event": "action", "skill": "x"})
    log.log({"event": "action", "skill": "y"})
    assert not p.exists()                       # no disk I/O while the activity happens
    log.flush()
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and '"synthetic": true' in lines[0]


def test_off_logger_never_touches_disk(tmp_path):
    p = tmp_path / "sub" / "actions.jsonl"
    log = JsonlActionLogger(p, mode="off")
    log.log({"event": "action"})
    log.flush()
    assert not p.exists() and not p.parent.exists()


def test_append_logger_writes_each_record_immediately(tmp_path):
    p = tmp_path / "actions.jsonl"
    log = JsonlActionLogger(p, mode="append")
    log.log({"event": "action"})
    assert p.exists() and len(p.read_text(encoding="utf-8").splitlines()) == 1
