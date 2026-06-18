# -*- coding: utf-8 -*-
"""Tkinter UI helpers for the match-value-output-field-name node."""

import tkinter as tk
from tkinter import ttk


MATCH_SOURCE_TYPE_VALUES = ["SQLite表", "中转副表"]
MATCH_MODE_VALUES = [
    "完全相等",
    "当前值包含匹配值",
    "匹配值包含当前值",
    "忽略大小写完全相等",
    "忽略大小写当前值包含匹配值",
    "忽略大小写匹配值包含当前值",
    "正则匹配",
]
MULTI_MATCH_POLICY_VALUES = ["合并所有字段名", "取第一个匹配字段名", "标记为多匹配"]


def build_match_value_header(frame):
    ttk.Label(
        frame,
        text="用当前表指定字段的值，去 SQLite 表或中转副表的多个字段列中匹配；匹配到哪个字段，就把该字段名输出到当前表的新列。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))


def get_match_value_table_choices(window, transit_context):
    try:
        sqlite_tables = window.app.get_table_names()
    except Exception:
        sqlite_tables = []
    transit_names = list(((transit_context or {}).get("transit_tables") or {}).keys())
    return sqlite_tables, transit_names


def build_match_value_source_section(window, frame, config, headers, sqlite_tables, transit_names):
    headers = list(headers or [])
    source_default = config.get("source_field") if config.get("source_field") in headers else (headers[0] if headers else "")
    source_var = window.add_labeled_combo(frame, "当前表匹配字段：", source_default, headers, 1, 0, 24, readonly=False)
    source_type_default = config.get("lookup_source_type", "SQLite表")
    if source_type_default not in MATCH_SOURCE_TYPE_VALUES:
        source_type_default = "SQLite表"
    source_type_var = window.add_labeled_combo(frame, "匹配来源：", source_type_default, MATCH_SOURCE_TYPE_VALUES, 1, 2, 16)
    initial_values = transit_names if source_type_default == "中转副表" else sqlite_tables
    table_label_text = "中转副表：" if source_type_default == "中转副表" else "SQLite匹配表："
    table_default = config.get("lookup_table") if config.get("lookup_table") in initial_values else (initial_values[0] if initial_values else config.get("lookup_table", ""))
    table_label = ttk.Label(frame, text=table_label_text)
    table_label.grid(row=1, column=4, sticky=tk.W, padx=4, pady=4)
    table_var = tk.StringVar(value=table_default)
    table_combo = ttk.Combobox(frame, textvariable=table_var, values=initial_values, width=28, state="normal")
    table_combo.grid(row=1, column=5, sticky=tk.W, padx=4, pady=4)
    mode_var = window.add_labeled_combo(frame, "匹配方式：", config.get("match_mode", "完全相等"), MATCH_MODE_VALUES, 2, 0, 26)
    window.sync_var_to_config(source_var, config, "source_field")
    window.sync_var_to_config(source_type_var, config, "lookup_source_type")
    window.sync_var_to_config(table_var, config, "lookup_table")
    window.sync_var_to_config(mode_var, config, "match_mode")
    return {
        "source_var": source_var,
        "source_type_var": source_type_var,
        "table_label": table_label,
        "table_var": table_var,
        "table_combo": table_combo,
        "mode_var": mode_var,
    }


def build_match_value_output_section(window, frame, config):
    out_frame = ttk.LabelFrame(frame, text="输出设置", padding=6)
    out_frame.grid(row=3, column=0, columnspan=8, sticky="ew", padx=4, pady=6)
    output_field_var = window.add_labeled_entry(out_frame, "输出字段名：", config.get("output_field", "匹配字段名"), 0, 0, 18)
    no_match_var = window.add_labeled_entry(out_frame, "未匹配写入：", config.get("no_match_value", "未匹配"), 0, 2, 18)
    sep_var = window.add_labeled_entry(out_frame, "多匹配分隔符：", config.get("multi_match_separator", ";"), 0, 4, 10)
    multi_var = window.add_labeled_combo(out_frame, "多匹配处理：", config.get("multi_match_policy", "合并所有字段名"), MULTI_MATCH_POLICY_VALUES, 1, 0, 18)
    window.sync_var_to_config(output_field_var, config, "output_field")
    window.sync_var_to_config(no_match_var, config, "no_match_value")
    window.sync_var_to_config(sep_var, config, "multi_match_separator")
    window.sync_var_to_config(multi_var, config, "multi_match_policy")

    match_value_bool = tk.BooleanVar(value=bool(config.get("output_match_value", True)))
    match_row_bool = tk.BooleanVar(value=bool(config.get("output_match_row", True)))
    status_bool = tk.BooleanVar(value=bool(config.get("output_status", True)))
    skip_empty_bool = tk.BooleanVar(value=bool(config.get("skip_empty_lookup_value", True)))
    ttk.Checkbutton(out_frame, text="输出匹配值", variable=match_value_bool).grid(row=2, column=0, sticky=tk.W, padx=4, pady=4)
    match_value_field_var = window.add_labeled_entry(out_frame, "匹配值字段：", config.get("match_value_field", "匹配值"), 2, 1, 16)
    ttk.Checkbutton(out_frame, text="输出匹配行号", variable=match_row_bool).grid(row=2, column=3, sticky=tk.W, padx=4, pady=4)
    match_row_field_var = window.add_labeled_entry(out_frame, "行号字段：", config.get("match_row_field", "匹配行号"), 2, 4, 16)
    ttk.Checkbutton(out_frame, text="输出匹配状态", variable=status_bool).grid(row=3, column=0, sticky=tk.W, padx=4, pady=4)
    status_field_var = window.add_labeled_entry(out_frame, "状态字段：", config.get("status_field", "匹配状态"), 3, 1, 16)
    ttk.Checkbutton(out_frame, text="跳过匹配表空值", variable=skip_empty_bool).grid(row=3, column=3, sticky=tk.W, padx=4, pady=4)
    for var, key in [
        (match_value_bool, "output_match_value"),
        (match_row_bool, "output_match_row"),
        (status_bool, "output_status"),
        (skip_empty_bool, "skip_empty_lookup_value"),
    ]:
        window.sync_bool_to_config(var, config, key)
    for var, key in [
        (match_value_field_var, "match_value_field"),
        (match_row_field_var, "match_row_field"),
        (status_field_var, "status_field"),
    ]:
        window.sync_var_to_config(var, config, key)
    return {
        "frame": out_frame,
        "output_field_var": output_field_var,
        "no_match_var": no_match_var,
        "sep_var": sep_var,
        "multi_var": multi_var,
        "match_value_bool": match_value_bool,
        "match_row_bool": match_row_bool,
        "status_bool": status_bool,
        "skip_empty_bool": skip_empty_bool,
        "match_value_field_var": match_value_field_var,
        "match_row_field_var": match_row_field_var,
        "status_field_var": status_field_var,
    }


def build_match_value_lookup_fields_section(frame):
    fields_frame = ttk.LabelFrame(frame, text="参与匹配的目标表字段", padding=6)
    fields_frame.grid(row=4, column=0, columnspan=8, sticky="nsew", padx=4, pady=6)
    fields_wrap = ttk.Frame(fields_frame)
    fields_wrap.pack(fill=tk.BOTH, expand=True)
    listbox = tk.Listbox(fields_wrap, selectmode=tk.MULTIPLE, height=10, exportselection=False)
    yscroll = ttk.Scrollbar(fields_wrap, orient=tk.VERTICAL, command=listbox.yview)
    listbox.configure(yscrollcommand=yscroll.set)
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    yscroll.pack(side=tk.RIGHT, fill=tk.Y)
    ttk.Label(fields_frame, text="说明：会逐行扫描这些字段的单元格；匹配成功后输出该单元格所在的字段名。", foreground="gray").pack(anchor=tk.W, padx=4, pady=(2, 0))
    return {
        "frame": fields_frame,
        "listbox": listbox,
    }


def sync_lookup_fields(fields_section, config):
    listbox = fields_section["listbox"]
    config["lookup_fields"] = [listbox.get(index) for index in listbox.curselection()]


def load_lookup_columns(window, config, transit_context, source_section, fields_section):
    lookup_table = source_section["table_var"].get().strip()
    lookup_source_type = source_section["source_type_var"].get().strip() or "SQLite表"
    columns = []
    if lookup_table:
        try:
            if lookup_source_type == "中转副表":
                item = ((transit_context or {}).get("transit_tables") or {}).get(lookup_table, {})
                columns = list(item.get("headers", []))
            else:
                columns = window.app.get_table_columns(lookup_table)
        except Exception:
            columns = []
    listbox = fields_section["listbox"]
    listbox.delete(0, tk.END)
    selected = set(config.get("lookup_fields", []))
    for index, column in enumerate(columns):
        listbox.insert(tk.END, column)
        if column in selected:
            listbox.selection_set(index)
    if not selected and columns:
        for index in range(min(3, len(columns))):
            listbox.selection_set(index)
        sync_lookup_fields(fields_section, config)


def build_lookup_field_action_buttons(window, config, transit_context, source_section, fields_section):
    listbox = fields_section["listbox"]
    btn_frame = ttk.Frame(fields_section["frame"])
    btn_frame.pack(fill=tk.X, pady=4)

    def select_all_fields():
        listbox.selection_set(0, tk.END)
        sync_lookup_fields(fields_section, config)

    def clear_fields():
        listbox.selection_clear(0, tk.END)
        sync_lookup_fields(fields_section, config)

    def refresh_fields():
        config["lookup_source_type"] = source_section["source_type_var"].get().strip() or "SQLite表"
        config["lookup_table"] = source_section["table_var"].get().strip()
        load_lookup_columns(window, config, transit_context, source_section, fields_section)

    def invert_fields():
        for index in range(listbox.size()):
            if listbox.selection_includes(index):
                listbox.selection_clear(index)
            else:
                listbox.selection_set(index)
        sync_lookup_fields(fields_section, config)

    listbox.bind("<<ListboxSelect>>", lambda *_: sync_lookup_fields(fields_section, config))
    ttk.Button(btn_frame, text="刷新字段", command=refresh_fields).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="全选", command=select_all_fields).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="全不选", command=clear_fields).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="反选", command=invert_fields).pack(side=tk.LEFT, padx=4)


def bind_match_value_source_events(window, config, transit_context, sqlite_tables, transit_names, source_section, fields_section):
    def get_current_lookup_values():
        return transit_names if source_section["source_type_var"].get() == "中转副表" else sqlite_tables

    def on_source_type_change(*_):
        source_type = source_section["source_type_var"].get().strip() or "SQLite表"
        config["lookup_source_type"] = source_type
        source_section["table_label"].configure(text="中转副表：" if source_type == "中转副表" else "SQLite匹配表：")
        values = get_current_lookup_values()
        source_section["table_combo"].configure(values=values)
        if source_section["table_var"].get().strip() not in values:
            source_section["table_var"].set(values[0] if values else "")
        config["lookup_table"] = source_section["table_var"].get().strip()
        load_lookup_columns(window, config, transit_context, source_section, fields_section)

    def on_table_change(*_):
        config["lookup_table"] = source_section["table_var"].get().strip()
        load_lookup_columns(window, config, transit_context, source_section, fields_section)

    source_section["source_type_var"].trace_add("write", on_source_type_change)
    source_section["table_var"].trace_add("write", on_table_change)


def build_match_value_output_field_name_config(window, config, headers, transit_context=None):
    frame = ttk.LabelFrame(window.config_frame, text="匹配值输出列名节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    build_match_value_header(frame)

    transit_context = transit_context or {"transit_tables": {}}
    headers = list(headers or [])
    sqlite_tables, transit_names = get_match_value_table_choices(window, transit_context)
    source_section = build_match_value_source_section(window, frame, config, headers, sqlite_tables, transit_names)
    build_match_value_output_section(window, frame, config)
    fields_section = build_match_value_lookup_fields_section(frame)
    build_lookup_field_action_buttons(window, config, transit_context, source_section, fields_section)
    bind_match_value_source_events(window, config, transit_context, sqlite_tables, transit_names, source_section, fields_section)
    load_lookup_columns(window, config, transit_context, source_section, fields_section)
