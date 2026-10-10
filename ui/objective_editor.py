"""Simple ordered-skill objective editor backed by YAML files."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from agent.config import ObjectiveData
from agent.objectives.storage import resolve_for_edit, save_as_new
from agent.skills.catalog import SKILL_CATALOG, SKILL_DEFINITIONS


class ObjectiveEditor:
    """Edit a copy of an objective and save it as a new YAML objective."""

    def __init__(self, parent: tk.Misc, directory: Path, objective: ObjectiveData,
                 on_saved: Callable[[str], None]):
        unsupported = [step.get("skill", "(missing)") for step in objective.plan
                       if step.get("skill") not in SKILL_DEFINITIONS]
        if unsupported:
            messagebox.showerror(
                "Objective not editable",
                "The objective uses skills outside this browsing editor: " + ", ".join(unsupported),
                parent=parent,
            )
            return
        self.directory, self.on_saved = directory, on_saved
        source = resolve_for_edit(objective)
        self.name = tk.StringVar(value=source["name"])
        self.plan: list[dict] = source["plan"]
        self.field_vars: dict[str, tk.StringVar] = {}
        self.field_frame: ttk.LabelFrame | None = None
        self._selected = -1

        self.window = tk.Toplevel(parent)
        self.window.title(f"Customize objective: {objective.name}")
        self.window.geometry("780x540")
        self.window.transient(parent)

        outer = ttk.Frame(self.window, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Draft objective", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Changes stay in this draft until you save it as a new objective.").pack(anchor="w", pady=(2, 10))

        name_row = ttk.Frame(outer)
        name_row.pack(fill="x", pady=(0, 10))
        ttk.Label(name_row, text="Objective name").pack(side="left")
        ttk.Entry(name_row, textvariable=self.name, width=42).pack(side="left", padx=(10, 0))

        content = ttk.Frame(outer)
        content.pack(fill="both", expand=True)
        left = ttk.Frame(content)
        left.pack(side="left", fill="both", expand=True)
        ttk.Label(left, text="Skills in run order").pack(anchor="w")
        self.steps = tk.Listbox(left, height=14, exportselection=False)
        self.steps.pack(fill="both", expand=True, pady=(4, 8))
        self.steps.bind("<<ListboxSelect>>", self._on_select)

        add_row = ttk.Frame(left)
        add_row.pack(fill="x")
        self.skill_choice = tk.StringVar(value=SKILL_CATALOG[0].label)
        ttk.Combobox(add_row, textvariable=self.skill_choice,
                     values=[definition.label for definition in SKILL_CATALOG],
                     state="readonly", width=24).pack(side="left")
        ttk.Button(add_row, text="Add skill", command=self._add).pack(side="left", padx=6)

        order_row = ttk.Frame(left)
        order_row.pack(anchor="w", pady=(8, 0))
        ttk.Button(order_row, text="Move up", command=lambda: self._move(-1)).pack(side="left")
        ttk.Button(order_row, text="Move down", command=lambda: self._move(1)).pack(side="left", padx=6)
        ttk.Button(order_row, text="Remove", command=self._remove).pack(side="left")

        self.field_frame = ttk.LabelFrame(content, text="Selected skill settings", padding=12)
        self.field_frame.pack(side="left", fill="both", expand=True, padx=(16, 0))
        self._show_fields(-1)

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(12, 0))
        ttk.Button(footer, text="Cancel draft", command=self.window.destroy).pack(side="right")
        ttk.Button(footer, text="Save as new objective", command=self._save).pack(side="right", padx=8)
        self._render_steps()

    def _on_select(self, _event=None) -> None:
        selection = self.steps.curselection()
        index = selection[0] if selection else -1
        self._commit_fields()
        self._selected = index
        self._show_fields(index)

    def _commit_fields(self) -> None:
        if self._selected < 0 or self._selected >= len(self.plan):
            return
        definition = SKILL_DEFINITIONS[self.plan[self._selected]["skill"]]
        self.plan[self._selected]["args"] = {
            field.name: self.field_vars[field.name].get()
            for field in definition.fields
        }

    def _show_fields(self, index: int) -> None:
        assert self.field_frame is not None
        for child in self.field_frame.winfo_children():
            child.destroy()
        self.field_vars.clear()
        if index < 0 or index >= len(self.plan):
            ttk.Label(self.field_frame, text="Select a skill to edit its settings.", wraplength=260).pack(anchor="w")
            return
        step = self.plan[index]
        definition = SKILL_DEFINITIONS[step["skill"]]
        ttk.Label(self.field_frame, text=definition.description, wraplength=270).pack(anchor="w", pady=(0, 10))
        if not definition.fields:
            ttk.Label(self.field_frame, text="This skill has no settings.").pack(anchor="w")
            return
        for field in definition.fields:
            ttk.Label(self.field_frame, text=field.label).pack(anchor="w", pady=(4, 0))
            variable = tk.StringVar(value=str(step.get("args", {}).get(field.name, field.default)))
            ttk.Entry(self.field_frame, textvariable=variable, width=34).pack(anchor="w", fill="x")
            self.field_vars[field.name] = variable

    def _render_steps(self, selection: int | None = None) -> None:
        self.steps.delete(0, tk.END)
        for index, step in enumerate(self.plan, start=1):
            definition = SKILL_DEFINITIONS[step["skill"]]
            self.steps.insert(tk.END, f"{index}. {definition.label}")
        if selection is not None and 0 <= selection < len(self.plan):
            self.steps.selection_set(selection)
            self.steps.activate(selection)
            self._selected = selection
            self._show_fields(selection)
        else:
            self._selected = -1
            self._show_fields(-1)

    def _add(self) -> None:
        self._commit_fields()
        skill_name = next(definition.name for definition in SKILL_CATALOG
                          if definition.label == self.skill_choice.get())
        definition = SKILL_DEFINITIONS[skill_name]
        self.plan.append({"skill": skill_name,
                          "args": {field.name: field.default for field in definition.fields}})
        self._render_steps(len(self.plan) - 1)

    def _move(self, direction: int) -> None:
        selection = self.steps.curselection()
        if not selection:
            return
        self._commit_fields()
        index = selection[0]
        destination = index + direction
        if not 0 <= destination < len(self.plan):
            return
        self.plan[index], self.plan[destination] = self.plan[destination], self.plan[index]
        self._render_steps(destination)

    def _remove(self) -> None:
        selection = self.steps.curselection()
        if not selection:
            return
        self._commit_fields()
        index = selection[0]
        self.plan.pop(index)
        self._render_steps(min(index, len(self.plan) - 1))

    def _save(self) -> None:
        self._commit_fields()
        try:
            path = save_as_new(self.directory, self.name.get(), self.plan)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Cannot save objective", str(exc), parent=self.window)
            return
        self.on_saved(self.name.get().strip())
        messagebox.showinfo("Objective saved", f"Saved as {path.name}.", parent=self.window)
        self.window.destroy()
