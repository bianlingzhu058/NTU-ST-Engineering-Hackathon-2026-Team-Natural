"""Append structured, explicitly labeled activity events as JSONL."""
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import uuid


class JsonlActionLogger:
    """Writes timestamped synthetic activity records to one JSONL file."""
    def __init__(self, path: Path, run_id: str | None = None):
        self._path, self._run_id, self._lock = path, run_id or str(uuid.uuid4()), threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def run_id(self) -> str: return self._run_id

    def log(self, event: dict) -> None:
        """Append one synthetic event with timestamp and run identifier."""
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), "run_id": self._run_id, "synthetic": True, **event}
        with self._lock, self._path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
