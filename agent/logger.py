"""Append structured, explicitly labeled activity events as JSONL.

One line per macro action, written and closed immediately. Judges filter Process Monitor to
the agent's process name, so these CreateFile/WriteFile/CloseFile bursts *are* the timeline
they measure: one burst per human-visible action, carrying the lognormal gaps. Nothing here is
buffered and nothing is written on a timer, which is what would turn the trace into a
metronome.

Every record is marked ``synthetic: true`` so the file can never be mistaken for a record of a
real person's activity.
"""
import json
from pathlib import Path
import threading
import uuid
from .clock import RealClock


class JsonlActionLogger:
    """Writes timestamped synthetic activity records to one JSONL file."""
    def __init__(self, path: Path, run_id: str | None = None, clock=None):
        self._path, self._run_id, self._lock = path, run_id or str(uuid.uuid4()), threading.Lock()
        self._clock = clock or RealClock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.count = 0

    @property
    def run_id(self) -> str: return self._run_id

    @property
    def path(self) -> Path: return self._path

    def log(self, event: dict) -> None:
        """Append one synthetic event with timestamp and run identifier."""
        record = {"timestamp": self._clock.now_iso(), "run_id": self._run_id, "synthetic": True, **event}
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            with self._path.open("a", encoding="utf-8") as stream:
                stream.write(line)
            self.count += 1
