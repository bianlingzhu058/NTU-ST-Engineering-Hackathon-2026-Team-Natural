"""Point-form responsibility: provide a small, explicit local operator interface.

- Lets an operator choose an objective and bounded duration.
- Defaults to dry-run mode; desktop control requires a deliberate opt-in.
- Calls the shared agent runtime and stops runs through its configured stop file.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from agent.app import build_app
from agent.config import ObjectiveData, load_objectives
from agent.skills.catalog import SKILL_DEFINITIONS
from agent.run_control import RunControl
from .objective_editor import ObjectiveEditor

ROOT = Path(__file__).resolve().parent.parent


class OperatorApp:
    """Tkinter controls and status display for a single local run."""

    def __init__(self, window: tk.Tk) -> None:
        self.window = window
        self.window.title("Synthetic Activity Harness")
        self.window.geometry("580x410")
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.stop_path: Path | None = None
        self.control: RunControl | None = None

        _, _, _, objectives = build_app(dry_run=True)
        self.objectives = objectives
        names = [item.name for item in objectives]
        default_name = "browse_internet" if "browse_internet" in names else (names[0] if names else "")
        self.objective = tk.StringVar(value=default_name)
        self.minutes = tk.StringVar(value="15")
        self.dry_run = tk.BooleanVar(value=True)
        self.authorized = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready - dry-run preview; no desktop input")
        self.run_id = tk.StringVar(value="No run yet")
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        panel = ttk.Frame(window, padding=16)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Synthetic Activity Harness", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(panel, text="Runs are labeled synthetic and written to the action log.").pack(anchor="w", pady=(2, 16))
        form = ttk.Frame(panel)
        form.pack(fill="x")
        ttk.Label(form, text="Objective").grid(row=0, column=0, sticky="w", pady=4)
        self.objective_combo = ttk.Combobox(form, textvariable=self.objective, values=names,
                                            state="readonly", width=28)
        self.objective_combo.grid(row=0, column=1, sticky="w", padx=8, pady=4)
        self.customize_button = ttk.Button(form, text="Customize selected...", command=self.customize_selected)
        self.customize_button.grid(row=0, column=2, sticky="w", padx=(8, 0), pady=4)
        ttk.Label(form, text="Duration (minutes, live run; max 120)").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(form, textvariable=self.minutes, width=10).grid(row=1, column=1, sticky="w", padx=8, pady=4)
        ttk.Checkbutton(panel, text="Dry run (no desktop input)", variable=self.dry_run,
                        command=self._update_status).pack(anchor="w", pady=(10, 2))
        ttk.Checkbutton(panel, text="I confirm this is an authorized, unlocked test VM",
                        variable=self.authorized).pack(anchor="w", pady=2)
        actions = ttk.Frame(panel)
        actions.pack(anchor="w", pady=12)
        self.start_button = ttk.Button(actions, text="Start run", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(actions, text="Stop run", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.pause_button = ttk.Button(actions, text="Pause", command=self.toggle_pause, state="disabled")
        self.pause_button.pack(side="left")
        ttk.Label(panel, textvariable=self.status, wraplength=500).pack(anchor="w", pady=(4, 2))
        self.progress = tk.StringVar(value="Scenario/skill: -")
        ttk.Label(panel, textvariable=self.progress, wraplength=500).pack(anchor="w", pady=(4, 2))
        ttk.Label(panel, text="Run ID:").pack(anchor="w", pady=(8, 0))
        ttk.Label(panel, textvariable=self.run_id, wraplength=500).pack(anchor="w")
        self.window.after(150, self._drain_events)

    def _update_status(self) -> None:
        mode = "dry-run preview; no desktop input" if self.dry_run.get() else "desktop input enabled"
        self.status.set("Ready - " + mode)

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        minutes = 0.0
        if not self.dry_run.get():
            try:
                minutes = float(self.minutes.get())
                if not 0 < minutes <= 120:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid duration", "Enter a duration greater than 0 and no more than 120 minutes.")
                return
        if not self.objective.get():
            messagebox.showerror("No scenarios", "No objectives were found in config/objectives/.")
            return
        if not self.dry_run.get() and not self.authorized.get():
            messagebox.showerror("Authorization required", "Confirm that this is an authorized, unlocked test VM.")
            return
        config, _, _, _ = build_app(dry_run=True)
        self.stop_path = ROOT / config.section("runner").get("stop_file", ".agent-stop")
        self.stop_path.unlink(missing_ok=True)
        self.control = RunControl(self.stop_path.exists)
        self.start_button.configure(state="disabled")
        self.customize_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.pause_button.configure(state="normal", text="Pause")
        self.status.set("Starting synthetic run...")
        self.worker = threading.Thread(target=self._run,
                                       args=(minutes, self.objective.get(), self.dry_run.get(), self.control), daemon=True)
        self.worker.start()

    def _run(self, minutes: float, objective: str, dry_run: bool, control: RunControl) -> None:
        try:
            _, context, runner, _ = build_app(root=ROOT, dry_run=dry_run, control=control,
                                              progress_callback=lambda scenario, skill: self.events.put(("progress", f"{scenario} / {skill}")))
            self.events.put(("run_id", context.logger.run_id))
            self.events.put(("status", "Running synthetic activity..."))
            if dry_run:
                runner.run_once(objective)
                count = len(context.backend.calls)
                if control.stopped:
                    message = f"Dry run stopped after simulating {count} input actions. No desktop input was sent."
                else:
                    message = f"Dry run complete: simulated {count} input actions. No desktop input was sent. See logs/actions.jsonl."
            else:
                runner.run(minutes, objective)
                stopped = self.stop_path is not None and self.stop_path.exists()
                message = "Run stopped." if stopped else "Run completed."
            self.events.put(("status", message))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            if self.stop_path:
                self.stop_path.unlink(missing_ok=True)
            self.events.put(("done", ""))

    def customize_selected(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        selected = next((item for item in self.objectives if item.name == self.objective.get()), None)
        if selected is None:
            messagebox.showerror("Objective unavailable", "Select an objective before opening the editor.")
            return
        directory = ROOT / "config" / "objectives"
        ObjectiveEditor(self.window, directory, selected, self._reload_objectives)

    def _reload_objectives(self, selected_name: str | None = None) -> None:
        try:
            self.objectives = load_objectives(ROOT / "config" / "objectives")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot reload objectives", str(exc))
            return
        names = [item.name for item in self.objectives]
        self.objective_combo.configure(values=names)
        if selected_name in names:
            self.objective.set(selected_name)
        elif names:
            self.objective.set(names[0])

    def stop(self) -> None:
        if self.worker and self.worker.is_alive() and self.stop_path:
            if self.control:
                self.control.stop()
            self.stop_path.touch(exist_ok=True)
            self.status.set("Stop requested; waiting for the current action to finish...")

    def toggle_pause(self) -> None:
        if not self.control or not (self.worker and self.worker.is_alive()):
            return
        if self.control.paused:
            self.control.resume()
            self.pause_button.configure(text="Pause")
            self.status.set("Run resumed.")
        else:
            self.control.pause()
            self.pause_button.configure(text="Resume")
            self.status.set("Pause requested; waiting for the current action to finish...")

    def close(self) -> None:
        """Request a clean stop before closing the operator window."""
        if self.worker and self.worker.is_alive():
            self.stop()
            self.status.set("Stopping the run before closing...")
            self.window.after(150, self._close_when_stopped)
        else:
            self.window.destroy()

    def _close_when_stopped(self) -> None:
        if self.worker and self.worker.is_alive():
            self.window.after(150, self._close_when_stopped)
        else:
            self.window.destroy()

    def _drain_events(self) -> None:
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "run_id":
                self.run_id.set(value)
            elif kind == "status":
                self.status.set(value)
            elif kind == "progress":
                self.progress.set("Scenario/skill: " + value)
            elif kind == "error":
                self.status.set("Run failed: " + value)
                messagebox.showerror("Run failed", value)
            elif kind == "done":
                self.start_button.configure(state="normal")
                self.customize_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
                self.pause_button.configure(state="disabled", text="Pause")
                self.progress.set("Scenario/skill: -")
        self.window.after(150, self._drain_events)


def main() -> None:
    """Start the local operator interface."""
    window = tk.Tk()
    OperatorApp(window)
    window.mainloop()


if __name__ == "__main__":
    main()
