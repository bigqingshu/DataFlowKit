# -*- coding: utf-8 -*-
"""Tkinter UI helpers for plugin schema parameter controls."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

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


def build_plugin_output_and_log_section(
    window,
    frame,
    config,
    item,
    params,
    headers,
    current_rows,
    transit_context,
    dynamic_param_controls,
    refresh_plugin_dynamic_controls,
    row,
):
    plugin_id = config.get("plugin_id", "")
    info = item.get("info", {})
    ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=row, column=0, columnspan=4, sticky="ew", pady=8)
    row += 1

    ttk.Label(frame, text="插件输出处理：", font=("TkDefaultFont", 10, "bold")).grid(row=row, column=0, columnspan=4, sticky=tk.W, padx=4, pady=(4, 2))
    row += 1
    output_choices = ["使用插件返回结果", "保存为中转副表并保持当前表", "保存为中转副表并使用插件返回结果", "追加字段到当前表"]
    output_var = window.add_labeled_combo(frame, "输出方式：", config.get("output_mode", "使用插件返回结果"), output_choices, row, 0, 28)
    output_var.trace_add("write", lambda *_, v=output_var: config.__setitem__("output_mode", v.get()))
    row += 1

    save_transit_var = tk.BooleanVar(value=bool(config.get("save_output_as_transit", False)))
    ttk.Checkbutton(frame, text="插件输出保存为中转副表", variable=save_transit_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=4, pady=4)
    save_transit_var.trace_add("write", lambda *_, v=save_transit_var: config.__setitem__("save_output_as_transit", bool(v.get())))
    ttk.Label(frame, text="中转名称：").grid(row=row, column=2, sticky=tk.W, padx=4, pady=4)
    transit_var = tk.StringVar(value=config.get("transit_name", info.get("name", plugin_id)))
    ttk.Entry(frame, textvariable=transit_var, width=24).grid(row=row, column=3, sticky=tk.W, padx=4, pady=4)
    transit_var.trace_add("write", lambda *_, v=transit_var: config.__setitem__("transit_name", v.get()))
    row += 1

    conflict_var = window.add_labeled_combo(frame, "中转同名处理：", config.get("transit_conflict_mode", "覆盖"), ["覆盖", "追加", "自动加时间戳"], row, 0, 18)
    conflict_var.trace_add("write", lambda *_, v=conflict_var: config.__setitem__("transit_conflict_mode", v.get()))
    fail_var = window.add_labeled_combo(frame, "插件失败时：", config.get("plugin_failure_policy", "停止工作流"), ["停止工作流", "保留原表继续", "输出错误表继续"], row, 2, 18)
    fail_var.trace_add("write", lambda *_, v=fail_var: config.__setitem__("plugin_failure_policy", v.get()))
    row += 1

    ttk.Label(frame, text="插件日志：", font=("TkDefaultFont", 10, "bold")).grid(row=row, column=0, columnspan=4, sticky=tk.W, padx=4, pady=(8, 2))
    row += 1
    log_file_var = tk.BooleanVar(value=bool(config.get("save_plugin_log_file", True)))
    ttk.Checkbutton(frame, text="保存详细日志到 logs/plugins", variable=log_file_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=4, pady=4)
    log_file_var.trace_add("write", lambda *_, v=log_file_var: config.__setitem__("save_plugin_log_file", bool(v.get())))
    log_sqlite_var = tk.BooleanVar(value=bool(config.get("save_plugin_log_sqlite", False)))
    ttk.Checkbutton(frame, text="写入 SQLite 日志表 _plugin_log", variable=log_sqlite_var).grid(row=row, column=2, columnspan=2, sticky=tk.W, padx=4, pady=4)
    log_sqlite_var.trace_add("write", lambda *_, v=log_sqlite_var: config.__setitem__("save_plugin_log_sqlite", bool(v.get())))
    row += 1
    log_transit_var = tk.BooleanVar(value=bool(config.get("save_plugin_log_transit", False)))
    ttk.Checkbutton(frame, text="日志保存为中转副表", variable=log_transit_var).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=4, pady=4)
    log_transit_var.trace_add("write", lambda *_, v=log_transit_var: config.__setitem__("save_plugin_log_transit", bool(v.get())))
    ttk.Label(frame, text="日志中转名：").grid(row=row, column=2, sticky=tk.W, padx=4, pady=4)
    log_transit_name_var = tk.StringVar(value=config.get("plugin_log_transit_name", f"{info.get('name', plugin_id)}_日志"))
    ttk.Entry(frame, textvariable=log_transit_name_var, width=24).grid(row=row, column=3, sticky=tk.W, padx=4, pady=4)
    log_transit_name_var.trace_add("write", lambda *_, v=log_transit_name_var: config.__setitem__("plugin_log_transit_name", v.get()))
    row += 1
    log_preview_var = tk.BooleanVar(value=bool(config.get("plugin_log_in_preview", False)))
    ttk.Checkbutton(frame, text="预览模式也写入插件日志文件/SQLite", variable=log_preview_var).grid(row=row, column=0, columnspan=4, sticky=tk.W, padx=4, pady=4)
    log_preview_var.trace_add("write", lambda *_, v=log_preview_var: config.__setitem__("plugin_log_in_preview", bool(v.get())))
    row += 1

    if callable(getattr(item.get("module"), "open_config_window", None)):
        def open_custom_config():
            try:
                window.run_plugin_custom_config_window(
                    item,
                    config,
                    params,
                    headers,
                    current_rows=current_rows,
                    transit_context=transit_context,
                    dynamic_param_controls=dynamic_param_controls,
                    refresh_dynamic_controls=refresh_plugin_dynamic_controls,
                )
            except Exception as exc:
                messagebox.showerror("插件设置窗口错误", str(exc))

        ttk.Button(frame, text="打开插件自带设置窗口", command=open_custom_config).grid(row=row, column=0, sticky=tk.W, padx=4, pady=8)
        row += 1

    ttk.Label(
        frame,
        text="插件节点会接收当前工作流表格，并返回新的表格；预览模式下 context['is_preview']=True。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=row, column=0, columnspan=4, sticky=tk.W, padx=4, pady=4)
    return row + 1
