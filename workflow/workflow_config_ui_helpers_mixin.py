# -*- coding: utf-8 -*-
"""Small Tkinter helper methods shared by workflow config UIs."""

import tkinter as tk
from tkinter import ttk


class WorkflowConfigUiHelpersMixin:
    """Compatibility methods for common workflow configuration controls."""

    def make_node_enabled_var(self, idx):
        var = tk.BooleanVar(value=self.nodes[idx].get("enabled", True))

        def on_change(*_):
            if 0 <= idx < len(self.nodes):
                self.nodes[idx]["enabled"] = bool(var.get())
                self.refresh_node_list(select_index=idx, reveal=True)

        var.trace_add("write", on_change)
        return var

    def add_labeled_entry(self, parent, label, value, row, col, width=20):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky=tk.W, padx=4, pady=4)
        var = tk.StringVar(value=value)
        ttk.Entry(parent, textvariable=var, width=width).grid(row=row, column=col + 1, sticky=tk.W, padx=4, pady=4)
        return var

    def add_labeled_combo(self, parent, label, value, values, row, col, width=20, readonly=True):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky=tk.W, padx=4, pady=4)
        var = tk.StringVar(value=value if value in values or not readonly else (values[0] if values else value))
        state = "readonly" if readonly else "normal"
        ttk.Combobox(textvariable=var, values=values, width=width, state=state, master=parent).grid(
            row=row,
            column=col + 1,
            sticky=tk.W,
            padx=4,
            pady=4,
        )
        return var

    def add_labeled_combo_control(self, parent, label, value, values, row, col, width=20, readonly=True):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky=tk.W, padx=4, pady=4)
        var = tk.StringVar(value=value if value in values or not readonly else (values[0] if values else value))
        state = "readonly" if readonly else "normal"
        combo = ttk.Combobox(parent, textvariable=var, values=values, width=width, state=state)
        combo.grid(row=row, column=col + 1, sticky=tk.W, padx=4, pady=4)
        return var, combo

    def refresh_combo_values(self, combo, var, values, keep_custom=True, fallback=""):
        values = [str(v) for v in (values or [])]
        current = str(var.get() or "")
        display_values = list(values)
        if current and current not in display_values and keep_custom:
            display_values = [current] + display_values
        combo.configure(values=display_values)
        if not current:
            var.set(fallback if fallback in values else (values[0] if values else fallback))
        elif current not in values and not keep_custom:
            var.set(fallback if fallback in values else (values[0] if values else fallback))

    def refresh_listbox_values(self, listbox, values, selected_values=None):
        selected_values = set(selected_values or [])
        listbox.delete(0, tk.END)
        selected_indices = []
        for i, value in enumerate(values or []):
            listbox.insert(tk.END, value)
            if value in selected_values:
                selected_indices.append(i)
        for i in selected_indices:
            listbox.selection_set(i)
        return selected_indices

    def sync_var_to_config(self, var, config, key, cast=str):
        def on_change(*_):
            try:
                config[key] = cast(var.get())
            except Exception:
                config[key] = var.get()

        var.trace_add("write", on_change)
        return var

    def sync_bool_to_config(self, var, config, key):
        def on_change(*_):
            config[key] = bool(var.get())

        var.trace_add("write", on_change)
        return var
