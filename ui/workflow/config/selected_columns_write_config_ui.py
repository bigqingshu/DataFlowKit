# -*- coding: utf-8 -*-
"""Tkinter UI helpers for the selected-columns write workflow node."""

import tkinter as tk
from tkinter import ttk, messagebox

from workflow.nodes.selected_columns_nodes import (
    SELECTED_COLUMNS_PREVIEW_HEADERS,
    normalize_selected_columns_write_mode,
)


SOURCE_TYPE_VALUES = ["当前工作流表", "SQLite表", "中转副表"]
TARGET_TYPE_VALUES = ["当前工作表", "SQLite表", "中转副表"]
WRITE_MODE_VALUES = [
    "局部覆盖，保留目标原行数",
    "清空目标字段后覆盖，保留目标原行数",
    "按来源完整结构覆盖",
    "覆盖重建目标表",
]
FIELD_NAME_MODE_VALUES = ["使用原字段名", "添加前缀", "添加后缀", "手动字段映射"]
OVERWRITE_VALUES = ["覆盖全部", "只写入空单元格", "目标已有值则跳过", "目标已有值且不同才覆盖"]


def ensure_selected_columns_write_config_defaults(config):
    defaults = {
        "source_type": "当前工作流表",
        "source_sqlite_table": "",
        "source_transit_table": "",
        "selected_fields": [],
        "target_type": "SQLite表",
        "target_table": "选定列结果",
        "target_transit_table": "选定列结果",
        "write_mode": "复制列到目标表新建字段",
        "field_name_mode": "使用原字段名",
        "target_prefix": "",
        "target_suffix": "",
        "field_mappings": [],
        "overwrite_rule": "只写入空单元格",
        "enable_write": False,
        "backup_before_write": True,
    }
    for key, value in defaults.items():
        config.setdefault(key, value)
    config["write_mode"] = normalize_selected_columns_write_mode(config.get("write_mode"))


def get_selected_columns_write_table_choices(window, transit_context):
    transit_tables = (transit_context or {}).get("transit_tables", {}) or {}
    transit_names = sorted(transit_tables.keys())
    try:
        sqlite_tables = window.app.get_table_names()
    except Exception:
        sqlite_tables = []
    return sqlite_tables, transit_names


def build_selected_columns_write_header(frame):
    ttk.Label(
        frame,
        text=(
            "说明：从当前表 / SQLite表 / 中转副表选择若干列，复制到当前工作表 / SQLite表 / 中转副表的新建/已有字段。"
            "节点内的“生成写入预览”只显示写入动作；勾选允许写入后，预览完整计划/预览到当前节点/执行计划均可触发本节点写入。"
        ),
        foreground="gray",
        wraplength=760,
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))


def build_selected_columns_source_target_section(window, frame, config, sqlite_tables, transit_names):
    source_type_var, source_type_combo = window.add_labeled_combo_control(
        frame,
        "来源类型：",
        config.get("source_type", "当前工作流表"),
        SOURCE_TYPE_VALUES,
        1,
        0,
        12,
    )
    sqlite_source_var, sqlite_source_combo = window.add_labeled_combo_control(
        frame,
        "SQLite来源表：",
        config.get("source_sqlite_table", ""),
        sqlite_tables,
        1,
        2,
        18,
        readonly=False,
    )
    transit_source_var, transit_source_combo = window.add_labeled_combo_control(
        frame,
        "中转来源表：",
        config.get("source_transit_table", ""),
        transit_names,
        2,
        0,
        18,
        readonly=False,
    )
    refresh_button = ttk.Button(frame, text="刷新表/字段")
    refresh_button.grid(row=2, column=2, sticky=tk.W, padx=4, pady=4)

    target_type_var, target_type_combo = window.add_labeled_combo_control(
        frame,
        "目标类型：",
        config.get("target_type", "SQLite表"),
        TARGET_TYPE_VALUES,
        3,
        0,
        12,
    )
    sqlite_target_var, sqlite_target_combo = window.add_labeled_combo_control(
        frame,
        "SQLite目标表：",
        config.get("target_table", "选定列结果"),
        sqlite_tables,
        3,
        2,
        18,
        readonly=False,
    )
    transit_target_var, transit_target_combo = window.add_labeled_combo_control(
        frame,
        "中转目标表：",
        config.get("target_transit_table", "选定列结果"),
        transit_names,
        4,
        0,
        18,
        readonly=False,
    )

    write_mode_var = window.add_labeled_combo(
        frame,
        "写入范围：",
        config.get("write_mode", "局部覆盖，保留目标原行数"),
        WRITE_MODE_VALUES,
        5,
        0,
        28,
    )
    name_mode_var, name_mode_combo = window.add_labeled_combo_control(
        frame,
        "字段命名：",
        config.get("field_name_mode", "使用原字段名"),
        FIELD_NAME_MODE_VALUES,
        5,
        2,
        14,
    )
    overwrite_var = window.add_labeled_combo(
        frame,
        "覆盖策略：",
        config.get("overwrite_rule", "只写入空单元格"),
        OVERWRITE_VALUES,
        6,
        0,
        18,
    )

    prefix_var = window.add_labeled_entry(frame, "前缀：", config.get("target_prefix", ""), 6, 2, 12)
    suffix_var = window.add_labeled_entry(frame, "后缀：", config.get("target_suffix", ""), 6, 4, 12)
    enable_write_var = tk.BooleanVar(value=bool(config.get("enable_write", False)))
    backup_var = tk.BooleanVar(value=bool(config.get("backup_before_write", True)))
    ttk.Checkbutton(frame, text="执行/预览计划时写入目标表", variable=enable_write_var).grid(row=7, column=0, columnspan=3, sticky=tk.W, padx=4, pady=4)
    ttk.Checkbutton(frame, text="写入SQLite前备份", variable=backup_var).grid(row=7, column=3, columnspan=2, sticky=tk.W, padx=4, pady=4)

    window.sync_var_to_config(source_type_var, config, "source_type")
    window.sync_var_to_config(sqlite_source_var, config, "source_sqlite_table")
    window.sync_var_to_config(transit_source_var, config, "source_transit_table")
    window.sync_var_to_config(target_type_var, config, "target_type")
    window.sync_var_to_config(sqlite_target_var, config, "target_table")
    window.sync_var_to_config(transit_target_var, config, "target_transit_table")
    window.sync_var_to_config(write_mode_var, config, "write_mode")
    window.sync_var_to_config(name_mode_var, config, "field_name_mode")
    window.sync_var_to_config(overwrite_var, config, "overwrite_rule")
    window.sync_var_to_config(prefix_var, config, "target_prefix")
    window.sync_var_to_config(suffix_var, config, "target_suffix")
    window.sync_bool_to_config(enable_write_var, config, "enable_write")
    window.sync_bool_to_config(backup_var, config, "backup_before_write")

    return {
        "source_type_var": source_type_var,
        "source_type_combo": source_type_combo,
        "sqlite_source_var": sqlite_source_var,
        "sqlite_source_combo": sqlite_source_combo,
        "transit_source_var": transit_source_var,
        "transit_source_combo": transit_source_combo,
        "refresh_button": refresh_button,
        "target_type_var": target_type_var,
        "target_type_combo": target_type_combo,
        "sqlite_target_var": sqlite_target_var,
        "sqlite_target_combo": sqlite_target_combo,
        "transit_target_var": transit_target_var,
        "transit_target_combo": transit_target_combo,
        "write_mode_var": write_mode_var,
        "name_mode_var": name_mode_var,
        "name_mode_combo": name_mode_combo,
        "overwrite_var": overwrite_var,
        "prefix_var": prefix_var,
        "suffix_var": suffix_var,
        "enable_write_var": enable_write_var,
        "backup_var": backup_var,
    }


def read_selected_columns_initial_source(window, config, headers, idx, transit_context):
    try:
        current_headers, current_rows = window.get_headers_rows_before(idx) if idx is not None else (headers, [])
    except Exception:
        current_headers, current_rows = headers, []
    try:
        return window.read_selected_columns_source_table(config, current_headers, current_rows, transit_context)
    except Exception as exc:
        return [], [], f"来源读取失败：{exc}"


def build_selected_columns_field_section(frame, config, source_headers, source_rows, source_name):
    fields_frame = ttk.LabelFrame(
        frame,
        text=f"1. 选择来源字段（来源：{source_name}，{len(source_rows)} 行 × {len(source_headers)} 列）",
        padding=6,
    )
    fields_frame.grid(row=8, column=0, columnspan=8, sticky="ew", padx=4, pady=6)

    field_list = tk.Listbox(fields_frame, selectmode=tk.MULTIPLE, width=46, height=6, exportselection=False)
    field_y = ttk.Scrollbar(fields_frame, orient=tk.VERTICAL, command=field_list.yview)
    field_list.configure(yscrollcommand=field_y.set)
    field_list.grid(row=0, column=0, rowspan=4, sticky="nsew", padx=4, pady=4)
    field_y.grid(row=0, column=1, rowspan=4, sticky="ns", pady=4)
    fields_frame.rowconfigure(0, weight=1)
    fields_frame.columnconfigure(0, weight=1)

    selected_set = set(config.get("selected_fields", []) or [])
    for index, header in enumerate(source_headers):
        field_list.insert(tk.END, header)
        if (header in selected_set) or (not selected_set and index < 3):
            field_list.selection_set(index)

    return {
        "frame": fields_frame,
        "field_list": field_list,
    }


def sync_selected_columns_selected_fields(field_section, config):
    field_list = field_section["field_list"]
    config["selected_fields"] = [field_list.get(index) for index in field_list.curselection()]


def build_selected_columns_field_action_buttons(field_section, config):
    field_list = field_section["field_list"]

    def sync_selected_fields(event=None):
        sync_selected_columns_selected_fields(field_section, config)

    def select_all_fields():
        field_list.selection_set(0, tk.END)
        sync_selected_fields()

    def clear_selected_fields():
        field_list.selection_clear(0, tk.END)
        sync_selected_fields()

    field_list.bind("<<ListboxSelect>>", sync_selected_fields)
    fields_frame = field_section["frame"]
    ttk.Button(fields_frame, text="全选字段", command=select_all_fields).grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
    ttk.Button(fields_frame, text="清空选择", command=clear_selected_fields).grid(row=1, column=2, sticky=tk.W, padx=4, pady=4)
    ttk.Button(fields_frame, text="保存当前选择", command=sync_selected_fields).grid(row=2, column=2, sticky=tk.W, padx=4, pady=4)


def build_selected_columns_mapping_section(frame, config, source_headers):
    mapping_frame = ttk.LabelFrame(frame, text="2. 手动字段映射（仅字段命名=手动字段映射时生效）", padding=6)
    mapping_frame.grid(row=9, column=0, columnspan=8, sticky="ew", padx=4, pady=6)
    src_var = tk.StringVar(value=source_headers[0] if source_headers else "")
    target_var = tk.StringVar(value="")
    ttk.Label(mapping_frame, text="来源字段：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
    src_combo = ttk.Combobox(mapping_frame, textvariable=src_var, values=source_headers, width=20, state="normal")
    src_combo.grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
    ttk.Label(mapping_frame, text="目标字段名：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
    ttk.Entry(mapping_frame, textvariable=target_var, width=22).grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)

    mapping_tree = ttk.Treeview(mapping_frame, columns=("来源字段", "目标字段"), show="headings", height=3)
    for col, width in [("来源字段", 170), ("目标字段", 170)]:
        mapping_tree.heading(col, text=col)
        mapping_tree.column(col, width=width, anchor=tk.W, stretch=False)
    mapping_tree.grid(row=1, column=0, columnspan=4, sticky="nsew", padx=4, pady=4)
    y_scroll = ttk.Scrollbar(mapping_frame, orient=tk.VERTICAL, command=mapping_tree.yview)
    mapping_tree.configure(yscrollcommand=y_scroll.set)
    y_scroll.grid(row=1, column=4, sticky="ns", pady=4)

    for item in config.get("field_mappings", []) or []:
        mapping_tree.insert("", tk.END, values=(item.get("source_field", ""), item.get("target_field", "")))

    return {
        "frame": mapping_frame,
        "src_var": src_var,
        "src_combo": src_combo,
        "target_var": target_var,
        "mapping_tree": mapping_tree,
    }


def sync_selected_columns_field_mappings(mapping_section, config):
    config["field_mappings"] = []
    mapping_tree = mapping_section["mapping_tree"]
    for iid in mapping_tree.get_children():
        source_field, target_field = mapping_tree.item(iid, "values")
        if source_field:
            config["field_mappings"].append({"source_field": str(source_field), "target_field": str(target_field or source_field)})


def build_selected_columns_mapping_action_buttons(mapping_section, config):
    mapping_tree = mapping_section["mapping_tree"]
    src_var = mapping_section["src_var"]
    target_var = mapping_section["target_var"]

    def add_field_mapping():
        source_field = src_var.get().strip()
        target_field = target_var.get().strip() or source_field
        if not source_field:
            return
        for iid in list(mapping_tree.get_children()):
            old_source, _old_target = mapping_tree.item(iid, "values")
            if old_source == source_field:
                mapping_tree.delete(iid)
        mapping_tree.insert("", tk.END, values=(source_field, target_field))
        sync_selected_columns_field_mappings(mapping_section, config)

    def delete_field_mapping():
        for iid in mapping_tree.selection():
            mapping_tree.delete(iid)
        sync_selected_columns_field_mappings(mapping_section, config)

    mapping_frame = mapping_section["frame"]
    ttk.Button(mapping_frame, text="添加/更新映射", command=add_field_mapping).grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
    ttk.Button(mapping_frame, text="删除选中映射", command=delete_field_mapping).grid(row=0, column=5, sticky=tk.W, padx=4, pady=4)


def build_selected_columns_preview_section(frame):
    preview_frame = ttk.LabelFrame(frame, text="3. 写入预览（仅本节点内部显示，不影响结果预览区）", padding=6)
    preview_frame.grid(row=10, column=0, columnspan=8, sticky="ew", padx=4, pady=6)
    preview_frame.configure(width=820, height=190)
    preview_frame.grid_propagate(False)

    preview_cols = tuple(SELECTED_COLUMNS_PREVIEW_HEADERS)
    preview_tree = ttk.Treeview(preview_frame, columns=preview_cols, show="headings", height=6)
    widths = {
        "来源表": 120,
        "来源行": 60,
        "来源字段": 110,
        "来源值": 150,
        "目标表": 120,
        "目标行": 60,
        "目标字段": 110,
        "原值": 130,
        "动作": 170,
    }
    for col in preview_cols:
        preview_tree.heading(col, text=col)
        preview_tree.column(col, width=widths.get(col, 120), anchor=tk.W, stretch=False)
    y_scroll = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=preview_tree.yview)
    x_scroll = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=preview_tree.xview)
    preview_tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
    preview_tree.grid(row=0, column=0, sticky="nsew")
    y_scroll.grid(row=0, column=1, sticky="ns")
    x_scroll.grid(row=1, column=0, sticky="ew")
    preview_frame.rowconfigure(0, weight=1)
    preview_frame.columnconfigure(0, weight=1)

    return {
        "frame": preview_frame,
        "preview_tree": preview_tree,
    }


def sync_selected_columns_control_config(controls, config):
    config["source_type"] = controls["source_type_var"].get()
    config["source_sqlite_table"] = controls["sqlite_source_var"].get()
    config["source_transit_table"] = controls["transit_source_var"].get()
    config["target_type"] = controls["target_type_var"].get()
    config["target_table"] = controls["sqlite_target_var"].get()
    config["target_transit_table"] = controls["transit_target_var"].get()
    config["field_name_mode"] = controls["name_mode_var"].get()


def refresh_selected_columns_write_sources(
    window,
    config,
    headers,
    idx,
    transit_context,
    state,
    controls,
    field_section,
    mapping_section,
    refresh_table_choices=False,
):
    if state["refreshing"]:
        return
    state["refreshing"] = True
    try:
        sync_selected_columns_selected_fields(field_section, config)
        sync_selected_columns_field_mappings(mapping_section, config)
        sync_selected_columns_control_config(controls, config)

        live_transit_context = transit_context
        if refresh_table_choices:
            try:
                state["sqlite_tables"][:] = window.app.get_table_names()
            except Exception:
                state["sqlite_tables"][:] = window.get_sqlite_table_names()
            try:
                live_transit_context = window.get_transit_context_before(idx) if idx is not None else transit_context
            except Exception:
                live_transit_context = transit_context
            state["transit_names"][:] = sorted((live_transit_context or {}).get("transit_tables", {}).keys())
            for combo, var in [
                (controls["sqlite_source_combo"], controls["sqlite_source_var"]),
                (controls["sqlite_target_combo"], controls["sqlite_target_var"]),
            ]:
                window.refresh_combo_values(
                    combo,
                    var,
                    state["sqlite_tables"],
                    keep_custom=True,
                    fallback=state["sqlite_tables"][0] if state["sqlite_tables"] else "",
                )
            for combo, var in [
                (controls["transit_source_combo"], controls["transit_source_var"]),
                (controls["transit_target_combo"], controls["transit_target_var"]),
            ]:
                window.refresh_combo_values(
                    combo,
                    var,
                    state["transit_names"],
                    keep_custom=True,
                    fallback=state["transit_names"][0] if state["transit_names"] else "",
                )

        try:
            current_headers, current_rows = window.get_headers_rows_before(idx) if idx is not None else (headers, [])
        except Exception:
            current_headers, current_rows = headers, []
        try:
            source_headers, source_rows, source_label = window.read_selected_columns_source_table(
                config,
                current_headers,
                current_rows,
                live_transit_context,
            )
        except Exception as exc:
            source_headers, source_rows, source_label = [], [], f"来源读取失败：{exc}"
        state["source"].update({"headers": list(source_headers), "rows": list(source_rows), "name": source_label})

        fields_frame = field_section["frame"]
        field_list = field_section["field_list"]
        fields_frame.configure(text=f"1. 选择来源字段（来源：{source_label}，{len(source_rows)} 行 × {len(source_headers)} 列）")
        field_list.configure(height=min(10, max(4, len(source_headers))))
        selected = config.get("selected_fields", []) or list(source_headers[:3])
        selected_indices = window.refresh_listbox_values(field_list, source_headers, selected)
        if not selected_indices and source_headers:
            for index in range(min(3, len(source_headers))):
                field_list.selection_set(index)
        sync_selected_columns_selected_fields(field_section, config)

        window.refresh_combo_values(
            mapping_section["src_combo"],
            mapping_section["src_var"],
            source_headers,
            keep_custom=False,
            fallback=source_headers[0] if source_headers else "",
        )
        window.status_var.set(f"选定列写入字段已局部刷新：来源 {source_label}，{len(source_headers)} 个字段。")
    finally:
        state["refreshing"] = False


def build_selected_columns_preview_buttons(
    window,
    frame,
    config,
    headers,
    idx,
    transit_context,
    field_section,
    mapping_section,
    preview_section,
    refresh_sources,
):
    preview_tree = preview_section["preview_tree"]

    def generate_node_write_preview():
        sync_selected_columns_selected_fields(field_section, config)
        sync_selected_columns_field_mappings(mapping_section, config)
        for iid in preview_tree.get_children():
            preview_tree.delete(iid)
        try:
            current_headers, current_rows = window.get_headers_rows_before(idx) if idx is not None else (headers, [])
            context = window.get_transit_context_before(idx) if idx is not None else transit_context
            _preview_headers, preview_rows = window.build_selected_columns_write_preview(
                config,
                current_headers,
                current_rows,
                context,
            )
            for row in preview_rows[:2000]:
                preview_tree.insert("", tk.END, values=row)
            window.status_var.set(f"已生成选定列写入预览：{len(preview_rows)} 条动作（最多显示 2000 条）。")
        except Exception as exc:
            messagebox.showerror("生成写入预览失败", str(exc))

    btn_frame = ttk.Frame(frame)
    btn_frame.grid(row=11, column=0, columnspan=8, sticky=tk.W, padx=4, pady=4)
    ttk.Button(btn_frame, text="生成写入预览", command=generate_node_write_preview).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_frame, text="刷新字段", command=lambda: refresh_sources(True)).pack(side=tk.LEFT, padx=4)
    ttk.Label(
        btn_frame,
        text="提示：不勾选写入时只透传数据；目标选“当前工作表”会把写入结果作为后续节点输入。",
        foreground="gray",
        wraplength=620,
    ).pack(side=tk.LEFT, padx=12)


def build_selected_columns_write_config(window, config, headers, idx=None, transit_context=None):
    ensure_selected_columns_write_config_defaults(config)
    transit_context = transit_context or {"transit_tables": {}}
    sqlite_tables, transit_names = get_selected_columns_write_table_choices(window, transit_context)

    frame = ttk.LabelFrame(window.config_frame, text="选定列写入指定表节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    build_selected_columns_write_header(frame)

    controls = build_selected_columns_source_target_section(window, frame, config, sqlite_tables, transit_names)
    source_headers, source_rows, source_name = read_selected_columns_initial_source(
        window,
        config,
        headers,
        idx,
        transit_context,
    )
    state = {
        "sqlite_tables": sqlite_tables,
        "transit_names": transit_names,
        "source": {"headers": list(source_headers), "rows": list(source_rows), "name": source_name},
        "refreshing": False,
    }

    field_section = build_selected_columns_field_section(frame, config, source_headers, source_rows, source_name)
    build_selected_columns_field_action_buttons(field_section, config)

    mapping_section = build_selected_columns_mapping_section(frame, config, source_headers)
    build_selected_columns_mapping_action_buttons(mapping_section, config)

    preview_section = build_selected_columns_preview_section(frame)

    def refresh_sources(refresh_table_choices=False):
        refresh_selected_columns_write_sources(
            window,
            config,
            headers,
            idx,
            transit_context,
            state,
            controls,
            field_section,
            mapping_section,
            refresh_table_choices=refresh_table_choices,
        )

    def schedule_refresh(*_):
        window.window.after_idle(lambda: refresh_sources(False))

    controls["refresh_button"].configure(command=lambda: refresh_sources(True))
    controls["source_type_var"].trace_add("write", schedule_refresh)
    controls["sqlite_source_var"].trace_add("write", schedule_refresh)
    controls["transit_source_var"].trace_add("write", schedule_refresh)

    build_selected_columns_preview_buttons(
        window,
        frame,
        config,
        headers,
        idx,
        transit_context,
        field_section,
        mapping_section,
        preview_section,
        refresh_sources,
    )
