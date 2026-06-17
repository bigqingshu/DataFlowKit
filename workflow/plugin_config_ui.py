# -*- coding: utf-8 -*-
"""Tkinter UI orchestration for plugin node configuration."""

import tkinter as tk
from tkinter import ttk

from workflow.plugin_config_helpers import build_plugin_input_table_choices


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
