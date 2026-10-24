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
from agent.hotkeys import GlobalHotkeys

ROOT = Path(__file__).resolve().parent.parent


class OperatorApp:
    """Tkinter controls and status display for a single local run."""

    def __init__(self, window: tk.Tk) -> None:
        self.window = window
        self.window.title("Synthetic Activity Harness")
        self.window.geometry("540x360")
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.stop_path: Path | None = None
        self.hotkeys = GlobalHotkeys(on_start=lambda: self.window.after(0, self.start),
                                     on_stop=lambda: self.window.after(0, self.stop))

        _, _, _, objectives = build_app(dry_run=True)
        # "all objectives" (shown) maps to the runner's "all" sentinel: every objective once
        # per cycle in a fixed order (see Runner.run). Handy for a demo.
        self._all_label = "all objectives"
        self._workday_label = "my workday (own to do list)"
        self._scenario_values = [self._workday_label, self._all_label] + [item.name for item in objectives]
        self.objective = tk.StringVar(value=self._workday_label)
        self.minutes = tk.StringVar(value="15")
        self.dry_run = tk.BooleanVar(value=True)
        self.authorized = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready - dry run is selected")
        self.run_id = tk.StringVar(value="No run yet")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        hotkeys_registered = self.hotkeys.start()

        panel = ttk.Frame(window, padding=16)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Synthetic Activity Harness", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(panel, text="Runs are labeled synthetic and written to the action log.").pack(anchor="w", pady=(2, 16))
        form = ttk.Frame(panel)
        form.pack(fill="x")
        ttk.Label(form, text="Scenario").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Combobox(form, textvariable=self.objective, values=self._scenario_values,
                     state="readonly", width=28).grid(row=0, column=1, sticky="w", padx=8, pady=4)
        ttk.Label(form, text="Duration (minutes, 3 to 540)").grid(row=1, column=0, sticky="w", pady=4)
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
        ttk.Label(panel, textvariable=self.status, wraplength=500).pack(anchor="w", pady=(4, 2))
        ttk.Label(panel, text="Shortcuts: Ctrl+Alt+F9 start · Ctrl+Alt+F10 stop").pack(anchor="w")
        if not hotkeys_registered:
            self.status.set("Global shortcuts unavailable (unsupported platform or shortcut already in use)")
        ttk.Label(panel, text="Run ID:").pack(anchor="w", pady=(8, 0))
        ttk.Label(panel, textvariable=self.run_id, wraplength=500).pack(anchor="w")
        self.window.after(150, self._drain_events)

    def _update_status(self) -> None:
        mode = "dry run; no desktop input" if self.dry_run.get() else "desktop input enabled"
        self.status.set("Ready - " + mode)

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            minutes = float(self.minutes.get())
            if not 0 < minutes <= 540:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid duration", "Enter a duration from 3 to 540 minutes (a full workday).")
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
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set("Starting synthetic run...")
        self.worker = threading.Thread(target=self._run,
                                       args=(minutes, self.objective.get(), self.dry_run.get()), daemon=True)
        self.worker.start()

    def _run(self, minutes: float, objective: str, dry_run: bool) -> None:
        try:
            workday = objective == self._workday_label
            # a workday dry run uses the simulated clock, so it finishes in seconds
            _, context, runner, _ = build_app(root=ROOT, dry_run=dry_run, sim=dry_run and workday)
            self.events.put(("run_id", context.logger.run_id))
            self.events.put(("status", "Running synthetic activity..."))
            if objective == self._workday_label:
                from agent.app import run_workday
                context.pacer.set_stop(lambda: self.stop_path is not None and self.stop_path.exists())
                run_workday(context, minutes, ROOT, sim=dry_run)
            else:
                runner.run(minutes, "all" if objective == self._all_label else objective)
            stopped = self.stop_path is not None and self.stop_path.exists()
            self.events.put(("status", "Run stopped." if stopped else "Run completed."))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            if self.stop_path:
                self.stop_path.unlink(missing_ok=True)
            self.events.put(("done", ""))

    def stop(self) -> None:
        if self.worker and self.worker.is_alive() and self.stop_path:
            self.stop_path.touch(exist_ok=True)
            self.status.set("Stop requested; waiting for the current action to finish...")

    def close(self) -> None:
        """Request a clean stop before closing the operator window."""
        self.hotkeys.stop()
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
            elif kind == "error":
                self.status.set("Run failed: " + value)
                messagebox.showerror("Run failed", value)
            elif kind == "done":
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
        self.window.after(150, self._drain_events)


def main() -> None:
    """Start the local operator interface."""
    window = tk.Tk()
    OperatorApp(window)
    window.mainloop()


if __name__ == "__main__":
    main()
