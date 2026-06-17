# -*- coding: utf-8 -*-
"""Tkinter UI orchestration for plugin node configuration."""

import copy
import os
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from workflow.plugin_config_helpers import (
    build_plugin_input_spec,
    build_plugin_input_table_choices,
    build_plugin_load_status_state,
    default_plugin_input_spec,
    ensure_plugin_input_specs,
    format_plugin_input_spec,
    normalize_plugin_run_mode,
)


def build_plugin_run_environment_section(window, frame, config, item, plugin_id, start_row=3):
    available_run_modes = item.get("available_run_modes") or ["主程序内置环境", "插件独立环境"]
    status_state = build_plugin_load_status_state(
        item.get("load_status", "可内置运行"),
        item.get("metadata_source", ""),
        item.get("import_error", ""),
    )
    row = start_row
    ttk.Label(frame, text=status_state["text"], foreground=status_state["foreground"], wraplength=1050).grid(row=row, column=0, columnspan=4, sticky=tk.W, padx=4, pady=2)
    row += 1
    if status_state["import_error_text"]:
        ttk.Label(frame, text=status_state["import_error_text"], foreground="#b26a00", wraplength=1050).grid(row=row, column=0, columnspan=4, sticky=tk.W, padx=4, pady=(0, 6))
        row += 1

    normalized_run_mode = normalize_plugin_run_mode(
        config.get("run_mode", item.get("run_mode_default", "主程序内置环境")),
        available_run_modes,
    )
    config["run_mode"] = normalized_run_mode
    run_mode_var = tk.StringVar(value=normalized_run_mode)
    ttk.Label(frame, text="运行环境：").grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)
    run_mode_combo = ttk.Combobox(frame, textvariable=run_mode_var, values=available_run_modes, state="readonly", width=18)
    run_mode_combo.grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)
    run_mode_var.trace_add("write", lambda *_, v=run_mode_var: config.__setitem__("run_mode", v.get()))
    ttk.Label(frame, text="独立环境适合插件依赖未打包进主程序的情况", foreground="gray").grid(row=row, column=2, columnspan=2, sticky=tk.W, padx=4, pady=4)
    row += 1

    external_python_var = tk.StringVar(value=config.get("external_python", ""))
    ttk.Label(frame, text="独立Python：").grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)
    ttk.Entry(frame, textvariable=external_python_var, width=58).grid(row=row, column=1, columnspan=2, sticky=tk.W, padx=4, pady=4)

    def choose_external_python(v=external_python_var):
        path = filedialog.askopenfilename(title="选择插件独立环境 python.exe", filetypes=[("Python", "python.exe;python"), ("所有文件", "*.*")])
        if path:
            v.set(path)

    ttk.Button(frame, text="选择", command=choose_external_python).grid(row=row, column=3, sticky=tk.W, padx=4, pady=4)
    external_python_var.trace_add("write", lambda *_, v=external_python_var: config.__setitem__("external_python", v.get()))
    row += 1

    env_dir_var = tk.StringVar(value=config.get("external_env_dir", window.get_plugin_env_dir(plugin_id)))
    ttk.Label(frame, text="环境目录：").grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)
    ttk.Entry(frame, textvariable=env_dir_var, width=58).grid(row=row, column=1, columnspan=2, sticky=tk.W, padx=4, pady=4)

    def open_env_dir(v=env_dir_var):
        path = v.get().strip() or window.get_plugin_env_dir(plugin_id)
        os.makedirs(path, exist_ok=True)
        try:
            os.startfile(path)
        except Exception as e:
            messagebox.showerror("打开失败", f"无法打开环境目录：\n{path}\n\n{e}")

    ttk.Button(frame, text="打开", command=open_env_dir).grid(row=row, column=3, sticky=tk.W, padx=4, pady=4)
    env_dir_var.trace_add("write", lambda *_, v=env_dir_var: config.__setitem__("external_env_dir", v.get()))
    row += 1

    entry_var = tk.StringVar(value=config.get("external_entry", item.get("external_entry", item.get("path", ""))))
    ttk.Label(frame, text="外部入口：").grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)
    ttk.Entry(frame, textvariable=entry_var, width=58).grid(row=row, column=1, columnspan=2, sticky=tk.W, padx=4, pady=4)

    def test_external_python(v=external_python_var):
        py = v.get().strip() or window.find_external_python(config, item, allow_current=True)
        try:
            out = subprocess.check_output([py, "--version"], stderr=subprocess.STDOUT, text=True, timeout=10)
            messagebox.showinfo("测试成功", out.strip())
        except Exception as e:
            messagebox.showerror("测试失败", str(e))

    ttk.Button(frame, text="测试环境", command=test_external_python).grid(row=row, column=3, sticky=tk.W, padx=4, pady=4)
    entry_var.trace_add("write", lambda *_, v=entry_var: config.__setitem__("external_entry", v.get()))
    return row + 1


def refresh_plugin_input_listbox(input_lb, config):
    input_lb.delete(0, tk.END)
    for spec in config.get("input_tables", []) or []:
        input_lb.insert(tk.END, format_plugin_input_spec(spec))


def open_plugin_input_spec_editor(
    window,
    config,
    index,
    sqlite_tables,
    transit_names,
    refresh_input_lb,
    refresh_plugin_dynamic_controls,
):
    specs = config.setdefault("input_tables", [])
    editing = index is not None and 0 <= index < len(specs)
    source_spec = copy.deepcopy(specs[index]) if editing else default_plugin_input_spec(len(specs), sqlite_tables, transit_names)
    win = tk.Toplevel(window.window)
    try:
        win.withdraw()
    except Exception:
        pass
    win.title("插件输入表设置")
    win.transient(window.window)
    body = ttk.Frame(win, padding=10)
    body.pack(fill=tk.BOTH, expand=True)

    alias_var = tk.StringVar(value=source_spec.get("alias", ""))
    source_type_var = tk.StringVar(value=source_spec.get("source_type", "SQLite表"))
    sqlite_var = tk.StringVar(value=source_spec.get("sqlite_table", source_spec.get("table", "")))
    transit_var = tk.StringVar(value=source_spec.get("transit_table", source_spec.get("table", "")))
    enabled_var = tk.BooleanVar(value=bool(source_spec.get("enabled", True)))

    ttk.Label(body, text="别名：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
    ttk.Entry(body, textvariable=alias_var, width=30).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
    ttk.Checkbutton(body, text="启用", variable=enabled_var).grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)

    ttk.Label(body, text="来源类型：").grid(row=1, column=0, sticky=tk.W, padx=4, pady=4)
    ttk.Combobox(
        body,
        textvariable=source_type_var,
        values=["当前工作流表", "SQLite表", "中转副表"],
        state="readonly",
        width=18,
    ).grid(row=1, column=1, sticky=tk.W, padx=4, pady=4)

    ttk.Label(body, text="SQLite表：").grid(row=2, column=0, sticky=tk.W, padx=4, pady=4)
    ttk.Combobox(body, textvariable=sqlite_var, values=sqlite_tables, width=34, state="normal").grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=4, pady=4)
    ttk.Label(body, text="中转副表：").grid(row=3, column=0, sticky=tk.W, padx=4, pady=4)
    ttk.Combobox(body, textvariable=transit_var, values=transit_names, width=34, state="normal").grid(row=3, column=1, columnspan=2, sticky=tk.W, padx=4, pady=4)
    ttk.Label(body, text="建议别名示例：文档读取表、新内容表。别名是插件读取多表时的键名。", foreground="gray", wraplength=520).grid(row=4, column=0, columnspan=3, sticky=tk.W, padx=4, pady=(4, 8))

    btns = ttk.Frame(body)
    btns.grid(row=5, column=0, columnspan=3, sticky=tk.E, padx=4, pady=4)

    def on_ok():
        new_spec = build_plugin_input_spec(
            alias_var.get(),
            source_type_var.get(),
            sqlite_var.get(),
            transit_var.get(),
            enabled_var.get(),
            fallback_index=len(specs),
        )
        if editing:
            specs[index] = new_spec
        else:
            specs.append(new_spec)
        config["input_tables"] = specs
        refresh_input_lb()
        win.destroy()
        refresh_plugin_dynamic_controls()

    ttk.Button(btns, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=4)
    ttk.Button(btns, text="取消", command=win.destroy).pack(side=tk.RIGHT, padx=4)

    def show_input_window():
        window.show_centered_toplevel(win, window.window)
        win.grab_set()

    win.after_idle(show_input_window)


def build_plugin_input_tables_section(
    window,
    frame,
    config,
    row,
    sqlite_tables,
    transit_names,
    refresh_plugin_dynamic_controls,
):
    input_specs = ensure_plugin_input_specs(config)
    input_frame = ttk.LabelFrame(frame, text="插件多表输入（可选）", padding=6)
    input_frame.grid(row=row, column=0, columnspan=4, sticky="ew", padx=4, pady=(4, 8))
    ttk.Label(
        input_frame,
        text="默认会传入当前工作流表；这里可额外传入 SQLite 表或中转副表，插件可从 input_data['tables'] / context['input_tables'] 按别名读取。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=0, column=0, columnspan=5, sticky=tk.W, padx=4, pady=(0, 4))
    input_lb = tk.Listbox(input_frame, height=4, width=88, exportselection=False)
    input_lb.grid(row=1, column=0, columnspan=4, sticky="ew", padx=4, pady=4)

    def refresh_input_lb():
        window.refresh_plugin_input_listbox(input_lb, config)

    def selected_input_index():
        sel = input_lb.curselection()
        return int(sel[0]) if sel else None

    def edit_input_spec(index=None):
        window.open_plugin_input_spec_editor(
            config,
            index,
            sqlite_tables,
            transit_names,
            refresh_input_lb,
            refresh_plugin_dynamic_controls,
        )

    def edit_selected_input():
        idx = selected_input_index()
        if idx is not None:
            edit_input_spec(idx)

    def delete_selected_input():
        idx = selected_input_index()
        specs = config.setdefault("input_tables", [])
        if idx is not None and 0 <= idx < len(specs):
            del specs[idx]
            refresh_input_lb()
            refresh_plugin_dynamic_controls()

    input_btns = ttk.Frame(input_frame)
    input_btns.grid(row=1, column=4, sticky=tk.NW, padx=4, pady=4)
    ttk.Button(input_btns, text="增加", command=lambda: edit_input_spec(None)).pack(fill=tk.X, pady=2)
    ttk.Button(input_btns, text="编辑", command=edit_selected_input).pack(fill=tk.X, pady=2)
    ttk.Button(input_btns, text="删除", command=delete_selected_input).pack(fill=tk.X, pady=2)
    ttk.Button(input_btns, text="刷新", command=lambda: (refresh_input_lb(), refresh_plugin_dynamic_controls())).pack(fill=tk.X, pady=2)
    refresh_input_lb()
    return {
        "input_specs": input_specs,
        "input_listbox": input_lb,
        "refresh_input_lb": refresh_input_lb,
        "next_row": row + 1,
    }


def build_plugin_node_config(window, config, headers, transit_context=None, current_rows=None):
    frame = ttk.LabelFrame(window.config_frame, text="外部插件节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    plugin_id = config.get("plugin_id", "")
    item = window.plugin_registry.get(plugin_id)
    if not item:
        ttk.Label(frame, text=f"插件未加载或缺失：{plugin_id}", foreground="red").grid(row=0, column=0, columnspan=4, sticky=tk.W, padx=4, pady=4)
        ttk.Label(frame, text="请将对应插件 .py 放入 plugins 目录后点击左侧“刷新插件”。", foreground="gray").grid(row=1, column=0, columnspan=4, sticky=tk.W, padx=4, pady=4)
        return

    info = item.get("info", {})
    params = config.setdefault("params", {})
    ttk.Label(frame, text=f"插件：{info.get('name', plugin_id)}", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, columnspan=4, sticky=tk.W, padx=4, pady=4)
    ttk.Label(frame, text=f"ID：{plugin_id}    版本：{info.get('version', '')}    分类：{info.get('category', '')}", foreground="gray").grid(row=1, column=0, columnspan=4, sticky=tk.W, padx=4, pady=2)
    ttk.Label(frame, text=info.get("description", ""), foreground="gray", wraplength=1050).grid(row=2, column=0, columnspan=4, sticky=tk.W, padx=4, pady=(0, 8))

    row = window.build_plugin_run_environment_section(frame, config, item, plugin_id, start_row=3)
    transit_context = window.plugin_config_context_with_live_transit(transit_context, include_rows=False)
    reuse_note = window.plugin_config_transit_reuse_note(transit_context)
    if reuse_note:
        ttk.Label(frame, text=reuse_note, foreground="#0f766e", wraplength=1050).grid(row=row, column=0, columnspan=4, sticky=tk.W, padx=4, pady=(2, 6))
        row += 1
    try:
        sqlite_tables = window.app.get_table_names()
    except Exception:
        sqlite_tables = window.get_sqlite_table_names()
    table_choices = build_plugin_input_table_choices(sqlite_tables, transit_context)

    dynamic_param_controls = []
    dynamic_context = window.create_plugin_dynamic_config_context(
        item,
        config,
        params,
        headers,
        transit_context,
        current_rows,
        dynamic_param_controls,
    )
    refresh_plugin_dynamic_controls = dynamic_context["refresh_plugin_dynamic_controls"]

    input_section = window.build_plugin_input_tables_section(
        frame,
        config,
        row,
        table_choices["sqlite_tables"],
        table_choices["transit_names"],
        refresh_plugin_dynamic_controls,
    )
    row = input_section["next_row"]

    schema = item.get("schema", [])
    row = window.build_plugin_schema_parameter_controls(
        frame,
        schema,
        config,
        params,
        headers,
        row,
        dynamic_param_controls,
        dynamic_context,
    )
    window.build_plugin_output_and_log_section(
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
    )
