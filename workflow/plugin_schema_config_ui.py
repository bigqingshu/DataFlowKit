# -*- coding: utf-8 -*-
"""Tkinter UI helpers for plugin schema parameter controls."""

import tkinter as tk
from tkinter import ttk, filedialog

from workflow.plugin_config_helpers import (
    build_plugin_dynamic_select_choices,
    build_plugin_field_select_initial_value,
    build_plugin_select_initial_value,
)


def build_plugin_schema_parameter_controls(
    window,
    frame,
    schema,
    config,
    params,
    headers,
    row,
    dynamic_param_controls,
    dynamic_context,
):
    if not schema:
        ttk.Label(frame, text="该插件没有声明参数。", foreground="gray").grid(row=row, column=0, columnspan=4, sticky=tk.W, padx=4, pady=4)
        return row + 1

    set_param = dynamic_context["set_param"]
    get_input_table_alias_choices = dynamic_context["get_input_table_alias_choices"]
    get_field_choices_for_table_param = dynamic_context["get_field_choices_for_table_param"]
    get_dynamic_parameter_choices = dynamic_context["get_dynamic_parameter_choices"]
    refresh_plugin_dynamic_controls = dynamic_context["refresh_plugin_dynamic_controls"]
    is_refreshing_dynamic_controls = dynamic_context["is_refreshing_dynamic_controls"]

    for spec in schema:
        if not isinstance(spec, dict):
            continue
        key = spec.get("name")
        if not key:
            continue
        label = spec.get("label", key)
        typ = spec.get("type", "text")
        default = spec.get("default", [] if typ == "multi_field_select" else "")
        value = params.get(key, default)
        ttk.Label(frame, text=f"{label}：").grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)

        if typ in ("text", "string", "regex", "textarea"):
            var = tk.StringVar(value="" if value is None else str(value))
            ttk.Entry(frame, textvariable=var, width=42).grid(row=row, column=1, columnspan=2, sticky=tk.W, padx=4, pady=4)
            var.trace_add("write", lambda *_, k=key, v=var: set_param(k, v.get()))
        elif typ == "number":
            var = tk.StringVar(value="" if value is None else str(value))
            ttk.Entry(frame, textvariable=var, width=18).grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)
            var.trace_add("write", lambda *_, k=key, v=var: set_param(k, v.get()))
        elif typ == "bool":
            var = tk.BooleanVar(value=bool(value))
            ttk.Checkbutton(frame, variable=var).grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)
            var.trace_add("write", lambda *_, k=key, v=var: set_param(k, bool(v.get())))
        elif typ == "select":
            choices = spec.get("choices", spec.get("options", []))
            var = tk.StringVar(value=build_plugin_select_initial_value(value, choices))
            ttk.Combobox(frame, textvariable=var, values=choices, width=28, state="readonly").grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)
            var.trace_add("write", lambda *_, k=key, v=var: set_param(k, v.get()))
        elif typ == "dynamic_select":
            choices = build_plugin_dynamic_select_choices(spec, value, get_dynamic_parameter_choices(spec, key))
            var = tk.StringVar(value=build_plugin_select_initial_value(value, choices))
            state = "normal" if spec.get("allow_custom", True) else "readonly"
            combo = ttk.Combobox(frame, textvariable=var, values=choices, width=28, state=state)
            combo.grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)
            dynamic_param_controls.append({"type": typ, "spec": spec, "key": key, "var": var, "combo": combo})
            var.trace_add("write", lambda *_, k=key, v=var: set_param(k, v.get()))
        elif typ == "input_table_select":
            choices = get_input_table_alias_choices()
            choices = build_plugin_dynamic_select_choices(spec, value, choices)
            var = tk.StringVar(value=build_plugin_select_initial_value(value, choices, fallback="当前表"))
            combo = ttk.Combobox(frame, textvariable=var, values=choices, width=28, state="readonly")
            combo.grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)
            dynamic_param_controls.append({"type": typ, "spec": spec, "key": key, "var": var, "combo": combo})

            def update_table_param(*_, k=key, v=var):
                set_param(k, v.get())
                if not is_refreshing_dynamic_controls():
                    refresh_plugin_dynamic_controls()

            var.trace_add("write", update_table_param)
        elif typ == "input_table_field_select":
            choices = get_field_choices_for_table_param(spec)
            default_value = spec.get("default", "")
            choices = build_plugin_dynamic_select_choices(spec, value, choices)
            var = tk.StringVar(value=build_plugin_field_select_initial_value(value, choices, default_value))
            state = "normal" if spec.get("allow_custom", True) else "readonly"
            combo = ttk.Combobox(frame, textvariable=var, values=choices, width=28, state=state)
            combo.grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)
            dynamic_param_controls.append({"type": typ, "spec": spec, "key": key, "var": var, "combo": combo})
            var.trace_add("write", lambda *_, k=key, v=var: set_param(k, v.get()))
        elif typ == "field_select":
            choices = list(headers)
            var = tk.StringVar(value=build_plugin_select_initial_value(value, choices))
            ttk.Combobox(frame, textvariable=var, values=choices, width=28, state="readonly").grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)
            var.trace_add("write", lambda *_, k=key, v=var: set_param(k, v.get()))
        elif typ == "multi_field_select":
            lb_frame = ttk.Frame(frame)
            lb_frame.grid(row=row, column=1, columnspan=3, sticky=tk.W, padx=4, pady=4)
            lb = tk.Listbox(lb_frame, selectmode=tk.MULTIPLE, height=min(7, max(3, len(headers))), width=38, exportselection=False)
            scr = ttk.Scrollbar(lb_frame, orient=tk.VERTICAL, command=lb.yview)
            lb.configure(yscrollcommand=scr.set)
            for header in headers:
                lb.insert(tk.END, header)
            selected = value if isinstance(value, list) else []
            for index, header in enumerate(headers):
                if header in selected:
                    lb.selection_set(index)
            lb.pack(side=tk.LEFT, fill=tk.BOTH)
            scr.pack(side=tk.LEFT, fill=tk.Y)

            def update_multi(event=None, k=key, lbox=lb):
                set_param(k, [lbox.get(index) for index in lbox.curselection()])

            lb.bind("<<ListboxSelect>>", update_multi)
        elif typ == "file_path":
            var = tk.StringVar(value="" if value is None else str(value))
            ttk.Entry(frame, textvariable=var, width=50).grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)

            def choose_file(v=var, k=key):
                path = filedialog.askopenfilename(title="选择文件")
                if path:
                    v.set(path)
                    set_param(k, path)

            ttk.Button(frame, text="选择", command=choose_file).grid(row=row, column=2, sticky=tk.W, padx=4, pady=4)
            var.trace_add("write", lambda *_, k=key, v=var: set_param(k, v.get()))
        elif typ == "folder_path":
            var = tk.StringVar(value="" if value is None else str(value))
            ttk.Entry(frame, textvariable=var, width=50).grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)

            def choose_folder(v=var, k=key):
                path = filedialog.askdirectory(title="选择文件夹")
                if path:
                    v.set(path)
                    set_param(k, path)

            ttk.Button(frame, text="选择", command=choose_folder).grid(row=row, column=2, sticky=tk.W, padx=4, pady=4)
            var.trace_add("write", lambda *_, k=key, v=var: set_param(k, v.get()))
        elif typ == "table_select":
            choices = window.get_sqlite_table_names()
            var = tk.StringVar(value=build_plugin_select_initial_value(value, choices))
            ttk.Combobox(frame, textvariable=var, values=choices, width=28, state="readonly").grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)
            var.trace_add("write", lambda *_, k=key, v=var: set_param(k, v.get()))
        else:
            var = tk.StringVar(value="" if value is None else str(value))
            ttk.Entry(frame, textvariable=var, width=42).grid(row=row, column=1, columnspan=2, sticky=tk.W, padx=4, pady=4)
            var.trace_add("write", lambda *_, k=key, v=var: set_param(k, v.get()))

        help_text = spec.get("help") or spec.get("description")
        if help_text:
            ttk.Label(frame, text=help_text, foreground="gray", wraplength=600).grid(row=row, column=3, sticky=tk.W, padx=4, pady=4)
        row += 1
    return row
