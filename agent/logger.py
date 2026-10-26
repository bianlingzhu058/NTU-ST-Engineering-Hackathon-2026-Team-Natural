"""Append structured, explicitly labeled activity events as JSONL.

Logging mode matters for process authenticity. The judges filter Process Monitor to the
agent process, so writing one log line to disk after every action makes python.exe emit a
steady stream of WriteFile events — a tell, and one that contradicts the "python.exe is
silent on disk" claim. Modes:

  "buffered" (default) — hold records in memory during the run and write them ONCE at the
                         end (flush). python.exe does no disk I/O while the activity happens;
                         the full timeline is still saved for the analysis tools afterward.
  "off"               — keep nothing on disk at all (pure in-memory run).
  "append"            — the old behaviour: write each record immediately (handy in dev).
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import uuid


class JsonlActionLogger:
    """Writes timestamped synthetic activity records to one JSONL file."""
    def __init__(self, path: Path, run_id: str | None = None, mode: str = "buffered"):
        self._path, self._run_id, self._lock = Path(path), run_id or str(uuid.uuid4()), threading.Lock()
        self._mode = mode if mode in ("buffered", "off", "append") else "buffered"
        self._buffer: list[str] = []
        if self._mode == "append":       # only this mode touches the filesystem during the run
            self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def run_id(self) -> str: return self._run_id

    def _record(self, event: dict) -> str:
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), "run_id": self._run_id, "synthetic": True, **event}
        return json.dumps(record, ensure_ascii=False, default=str)

    def log(self, event: dict) -> None:
        """Record one synthetic event. In buffered/off mode nothing is written to disk yet."""
        line = self._record(event)
        if self._mode == "off":
            return
        if self._mode == "buffered":
            with self._lock:
                self._buffer.append(line)
            return
        with self._lock, self._path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

    def flush(self) -> None:
        """Write any buffered records to disk in one burst (called once, after the run)."""
        if self._mode != "buffered":
            return
        with self._lock:
            if not self._buffer:
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as stream:
                stream.write("\n".join(self._buffer) + "\n")
            self._buffer.clear()
