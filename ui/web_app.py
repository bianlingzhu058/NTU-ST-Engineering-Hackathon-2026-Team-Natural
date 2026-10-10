"""Loopback-only web operator interface for the Windows test VM."""
from __future__ import annotations

import hmac
import json
import logging
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from agent.app import build_app
from agent.config import load_objectives
from agent.objectives.storage import resolve_for_edit, save_as_new
from agent.run_control import RunControl
from agent.skills.catalog import SKILL_CATALOG

ROOT = Path(__file__).resolve().parent.parent
OBJECTIVES_DIR = ROOT / "config" / "objectives"
HOST = "127.0.0.1"
PORT = 4000


class RunService:
    """Own one background run and expose a small JSON-safe status snapshot."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._worker: threading.Thread | None = None
        self._control: RunControl | None = None
        self._state = {
            "running": False,
            "paused": False,
            "status": "Ready - dry-run preview; no desktop input",
            "run_id": None,
            "scenario": None,
            "skill": None,
            "dry_run": True,
        }

    def snapshot(self) -> dict:
        with self._lock:
            state = dict(self._state)
            if self._control is not None:
                state["paused"] = self._control.paused
            return state

    def start(self, objective_name: str, minutes: float, dry_run: bool, authorized: bool) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                raise ValueError("A run is already in progress.")
            if not any(item.name == objective_name for item in load_objectives(OBJECTIVES_DIR)):
                raise ValueError("Select an available objective.")
            if not dry_run and not authorized:
                raise ValueError("Confirm this is an authorized, unlocked test VM before enabling desktop input.")
            if not dry_run and not 0 < minutes <= 120:
                raise ValueError("Live-run duration must be greater than 0 and no more than 120 minutes.")

            stop_path = ROOT / ".agent-stop"
            stop_path.unlink(missing_ok=True)
            self._control = RunControl(stop_path.exists)
            self._state = {
                "running": True,
                "paused": False,
                "status": "Starting dry-run preview..." if dry_run else "Starting live run...",
                "run_id": None,
                "scenario": objective_name,
                "skill": None,
                "dry_run": dry_run,
            }
            self._worker = threading.Thread(
                target=self._execute,
                args=(objective_name, minutes, dry_run, self._control),
                name="objective-runner",
                daemon=True,
            )
            self._worker.start()

    def _progress(self, scenario: str, skill: str) -> None:
        with self._lock:
            self._state["scenario"] = scenario
            self._state["skill"] = skill

    def _execute(self, objective_name: str, minutes: float, dry_run: bool, control: RunControl) -> None:
        stop_path = ROOT / ".agent-stop"
        try:
            _, context, runner, _ = build_app(
                root=ROOT,
                dry_run=dry_run,
                control=control,
                progress_callback=self._progress,
            )
            with self._lock:
                self._state["run_id"] = context.logger.run_id
                self._state["status"] = "Previewing objective..." if dry_run else "Running objective..."

            if dry_run:
                runner.run_once(objective_name)
                count = len(context.backend.calls)
                status = (f"Dry run stopped after simulating {count} input actions. No desktop input was sent."
                          if control.stopped else
                          f"Dry run complete: simulated {count} input actions. No desktop input was sent. See logs/actions.jsonl.")
            else:
                runner.run(minutes, objective_name)
                status = "Run stopped." if control.stopped else "Run completed."
        except Exception as exc:
            status = f"Run failed: {exc}"
            logging.getLogger(__name__).exception("Objective run failed")
        finally:
            stop_path.unlink(missing_ok=True)
            with self._lock:
                self._state["running"] = False
                self._state["paused"] = False
                self._state["status"] = status
                self._state["scenario"] = None
                self._state["skill"] = None

    def control(self, action: str) -> None:
        with self._lock:
            if not self._state["running"] or self._control is None:
                raise ValueError("There is no active run to control.")
            if action == "pause":
                self._control.pause()
                self._state["status"] = "Pause requested; waiting for the current action to finish..."
            elif action == "resume":
                self._control.resume()
                self._state["status"] = "Run resumed."
            elif action == "stop":
                self._control.stop()
                self._state["status"] = "Stop requested; waiting for the current action to finish..."
                (ROOT / ".agent-stop").touch(exist_ok=True)
            else:
                raise ValueError("Unknown run-control action.")
            self._state["paused"] = self._control.paused


SERVICE = RunService()
CSRF_TOKEN = secrets.token_urlsafe(32)


def _objective_payloads() -> list[dict]:
    supported = {definition.name for definition in SKILL_CATALOG}
    payloads = []
    for objective in load_objectives(OBJECTIVES_DIR):
        editable = all(step.get("skill") in supported for step in objective.plan)
        payload = {"name": objective.name, "weight": objective.weight, "editable": editable}
        if editable:
            payload["draft"] = resolve_for_edit(objective)
        payloads.append(payload)
    return payloads


class OperatorRequestHandler(BaseHTTPRequestHandler):
    server_version = "SyntheticActivityUI/1.0"
    sys_version = ""

    def log_message(self, fmt: str, *args) -> None:
        logging.getLogger("ui.web").info("%s - %s", self.address_string(), fmt % args)

    def _send(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, value: dict | list) -> None:
        self._send(status, json.dumps(value).encode("utf-8"), "application/json; charset=utf-8")

    def _host_is_local(self) -> bool:
        return self.headers.get("Host", "").lower() in {
            f"localhost:{PORT}", f"127.0.0.1:{PORT}", f"[::1]:{PORT}"
        }

    def _authorized_post(self) -> bool:
        origin = self.headers.get("Origin")
        valid_origins = {f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"}
        supplied_token = self.headers.get("X-UI-Token", "")
        return (origin in valid_origins and
                hmac.compare_digest(supplied_token, CSRF_TOKEN))

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid request length.") from exc
        if length <= 0 or length > 1_000_000:
            raise ValueError("Request body must be between 1 byte and 1 MB.")
        try:
            value = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Request body must be valid JSON.") from exc
        if not isinstance(value, dict):
            raise ValueError("Request body must be a JSON object.")
        return value

    def do_GET(self) -> None:
        if not self._host_is_local():
            self._json(403, {"error": "Host is not allowed."})
            return
        route = urlsplit(self.path).path
        if route == "/":
            page = (Path(__file__).with_name("index.html").read_text(encoding="utf-8")
                    .replace("__UI_TOKEN__", CSRF_TOKEN).encode("utf-8"))
            self._send(200, page, "text/html; charset=utf-8")
        elif route == "/api/state":
            self._json(200, SERVICE.snapshot())
        elif route == "/api/objectives":
            skills = [{"name": item.name, "label": item.label, "description": item.description,
                       "fields": [field.__dict__ for field in item.fields]}
                      for item in SKILL_CATALOG]
            self._json(200, {"objectives": _objective_payloads(), "skills": skills})
        else:
            self._json(404, {"error": "Not found."})

    def do_POST(self) -> None:
        if not self._host_is_local():
            self._json(403, {"error": "Host is not allowed."})
            return
        if not self._authorized_post():
            self._json(403, {"error": "Request origin or UI token is not valid."})
            return
        route = urlsplit(self.path).path
        try:
            body = self._read_json()
            if route == "/api/run":
                name = str(body.get("objective", ""))
                dry_run_value = body.get("dry_run", True)
                if not isinstance(dry_run_value, bool):
                    raise ValueError("dry_run must be true or false.")
                dry_run = dry_run_value
                minutes = float(body.get("minutes", 15))
                authorized = body.get("authorized", False) is True
                SERVICE.start(name, minutes, dry_run, authorized)
                self._json(202, {"ok": True})
            elif route == "/api/control":
                SERVICE.control(str(body.get("action", "")))
                self._json(200, {"ok": True})
            elif route == "/api/objectives":
                path = save_as_new(OBJECTIVES_DIR, str(body.get("name", "")), body.get("plan", []))
                self._json(201, {"ok": True, "filename": path.name})
            else:
                self._json(404, {"error": "Not found."})
        except (OSError, TypeError, ValueError) as exc:
            self._json(400, {"error": str(exc)})


class LocalOperatorServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = LocalOperatorServer((HOST, PORT), OperatorRequestHandler)
    print(f"Operator UI is available at http://localhost:{PORT} (this VM only). Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping operator UI server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
