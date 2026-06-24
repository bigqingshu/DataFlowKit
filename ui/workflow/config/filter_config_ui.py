# -*- coding: utf-8 -*-
"""Tkinter UI orchestration for the advanced filter workflow node configuration."""

import tkinter as tk
from tkinter import ttk, messagebox

from workflow.filter_config_helpers import (
    apply_treeview_cell_edit,
    build_filter_actual_output_text,
    build_filter_condition_input_state,
    build_filter_field_refresh_state,
    build_filter_field_refresh_status,
    build_filter_join_input_state,
    build_filter_risk_display_state,
    build_filter_selectable_tables,
    build_treeview_cell_edit_state,
    append_filter_condition_row_via_service,
    append_filter_join_rule_row_via_service,
    delete_filter_condition_rows_via_service,
    delete_filter_join_rule_rows_via_service,
    ensure_filter_config_defaults,
    filter_conditions_from_rows,
    filter_conditions_to_rows,
    filter_dedupe_button_text,
    filter_join_rules_from_rows,
    filter_join_rules_to_rows,
    invert_filter_output_fields_by_indexes,
    select_all_filter_output_fields,
    select_current_table_filter_output_fields,
    toggle_filter_dedupe_config,
)


def build_filter_header_risk_section(window, frame, start_row=0):
    note = (
        "说明：上一步结果会作为【当前表】参与匹配。"
        "需要多表匹配时，在左侧勾选副表，再添加匹配规则，例如 当前表.编码 等于 物料表.编码。"
    )
    ttk.Label(frame, text=note, foreground="gray", wraplength=1050).grid(
        row=start_row,
        column=0,
        columnspan=8,
        sticky=tk.W,
        padx=4,
        pady=(0, 6),
    )

    risk_var = tk.StringVar()
    risk_label = ttk.Label(frame, textvariable=risk_var, wraplength=1050)
    risk_label.grid(row=start_row + 1, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))
    return {
        "risk_var": risk_var,
        "risk_label": risk_label,
        "next_row": start_row + 2,
    }


def build_filter_source_table_section(window, frame, config, headers, selected_tables, transit_context, sync_extra_tables, start_row=2):
    source_frame = ttk.LabelFrame(frame, text="1. 副表选择（主输入固定为：上一步结果 / 当前表）", padding=6)
    source_frame.grid(row=start_row, column=0, columnspan=8, sticky="nsew", pady=6)
    ttk.Label(source_frame, text=f"当前表字段数：{len(headers)}").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
    ttk.Label(source_frame, text="可选数据库表：").grid(row=1, column=0, sticky=tk.NW, padx=4, pady=4)
    table_list = tk.Listbox(source_frame, selectmode=tk.MULTIPLE, height=5, exportselection=False, width=36)
    table_list.grid(row=1, column=1, sticky="nsew", padx=4, pady=4)
    table_scroll = ttk.Scrollbar(source_frame, orient=tk.VERTICAL, command=table_list.yview)
    table_scroll.grid(row=1, column=2, sticky="ns")
    table_list.configure(yscrollcommand=table_scroll.set)

    try:
        db_tables = window.app.get_table_names()
    except Exception:
        db_tables = []
    transit_names = sorted((transit_context or {}).get("transit_tables", {}).keys())
    selectable_tables = build_filter_selectable_tables(db_tables, transit_names)
    for index, table in enumerate(selectable_tables):
        table_list.insert(tk.END, table)
        if table in selected_tables:
            table_list.selection_set(index)

    limit_var = window.add_labeled_entry(source_frame, "结果行数上限：", config.get("result_limit", "5000"), 0, 3, 10)
    max_var = window.add_labeled_entry(source_frame, "中间组合上限：", config.get("max_intermediate", "200000"), 0, 5, 12)
    window.sync_var_to_config(limit_var, config, "result_limit")
    window.sync_var_to_config(max_var, config, "max_intermediate")

    ttk.Button(source_frame, text="保存表选择 / 刷新字段", command=lambda: sync_extra_tables(True)).grid(row=1, column=3, sticky=tk.W, padx=4, pady=4)
    ttk.Button(source_frame, text="清空副表", command=lambda: (table_list.selection_clear(0, tk.END), sync_extra_tables(True))).grid(row=1, column=4, sticky=tk.W, padx=4, pady=4)
    return {
        "frame": source_frame,
        "table_list": table_list,
        "selectable_tables": selectable_tables,
        "limit_var": limit_var,
        "max_var": max_var,
    }


def build_filter_condition_section(window, frame, config, all_fields, start_row=3):
    condition_frame = ttk.LabelFrame(frame, text="2. 筛选条件（可筛选字段，并支持固定值或字段值匹配）", padding=6)
    condition_frame.grid(row=start_row, column=0, columnspan=8, sticky="nsew", pady=6)
    logic_var = window.add_labeled_combo(condition_frame, "条件关系：", config.get("logic", "AND"), window.LOGIC_TYPES, 0, 0, 8)
    window.sync_var_to_config(logic_var, config, "logic")
    condition_input_state = build_filter_condition_input_state(all_fields)
    field_var = tk.StringVar(value=condition_input_state["field_default"])
    op_var = tk.StringVar(value="包含")
    value_source_var = tk.StringVar(value=condition_input_state["value_source"])
    value_var = tk.StringVar(value=condition_input_state["value_default"])

    ttk.Label(condition_frame, text="字段：").grid(row=1, column=0, padx=4, pady=4)
    field_combo = ttk.Combobox(condition_frame, textvariable=field_var, values=all_fields, width=28, state="normal")
    field_combo.grid(row=1, column=1, padx=4, pady=4)
    ttk.Label(condition_frame, text="操作：").grid(row=1, column=2, padx=4, pady=4)
    ttk.Combobox(condition_frame, textvariable=op_var, values=window.FILTER_OPS, width=14, state="readonly").grid(row=1, column=3, padx=4, pady=4)
    ttk.Label(condition_frame, text="值来源：").grid(row=1, column=4, padx=4, pady=4)
    value_source_combo = ttk.Combobox(condition_frame, textvariable=value_source_var, values=window.FILTER_VALUE_SOURCES, width=10, state="readonly")
    value_source_combo.grid(row=1, column=5, padx=4, pady=4)
    ttk.Label(condition_frame, text="匹配值：").grid(row=1, column=6, padx=4, pady=4)
    value_combo = ttk.Combobox(condition_frame, textvariable=value_var, values=[], width=28, state="normal")
    value_combo.grid(row=1, column=7, padx=4, pady=4)

    cond_toolbar = ttk.Frame(condition_frame)
    cond_toolbar.grid(row=2, column=0, columnspan=7, sticky="w", padx=4, pady=(2, 0))
    cond_edit_mode = tk.BooleanVar(value=False)
    cond_edit_text = tk.StringVar(value="修改模式:关")

    def toggle_cond_edit_mode():
        cond_edit_mode.set(not cond_edit_mode.get())
        cond_edit_text.set("修改模式:开" if cond_edit_mode.get() else "修改模式:关")

    ttk.Button(cond_toolbar, textvariable=cond_edit_text, command=toggle_cond_edit_mode).pack(side=tk.LEFT, padx=2)
    ttk.Label(cond_toolbar, text="开启修改模式后可双击列表编辑；值来源=字段值时，匹配值请选择 当前表.字段 或 副表.字段。", foreground="gray").pack(side=tk.LEFT, padx=8)

    cond_tree = ttk.Treeview(condition_frame, columns=("字段", "操作", "值来源", "匹配值"), show="headings", height=6)
    for column, width in [("字段", 250), ("操作", 110), ("值来源", 90), ("匹配值", 250)]:
        cond_tree.heading(column, text=column)
        cond_tree.column(column, width=width, anchor=tk.W)
    cond_y_scroll = ttk.Scrollbar(condition_frame, orient=tk.VERTICAL, command=cond_tree.yview)
    cond_x_scroll = ttk.Scrollbar(condition_frame, orient=tk.HORIZONTAL, command=cond_tree.xview)
    cond_tree.configure(yscrollcommand=cond_y_scroll.set, xscrollcommand=cond_x_scroll.set)
    cond_tree.grid(row=3, column=0, columnspan=8, sticky="nsew", padx=4, pady=4)
    cond_y_scroll.grid(row=3, column=8, sticky="ns", pady=4)
    cond_x_scroll.grid(row=4, column=0, columnspan=8, sticky="ew", padx=4)
    condition_frame.rowconfigure(3, weight=1)
    condition_frame.columnconfigure(7, weight=1)
    for row_values in filter_conditions_to_rows(config.get("conditions", [])):
        cond_tree.insert("", tk.END, values=row_values)

    return {
        "frame": condition_frame,
        "logic_var": logic_var,
        "field_var": field_var,
        "field_combo": field_combo,
        "op_var": op_var,
        "value_source_var": value_source_var,
        "value_source_combo": value_source_combo,
        "value_var": value_var,
        "value_combo": value_combo,
        "cond_edit_mode": cond_edit_mode,
        "cond_tree": cond_tree,
        "button_row": 5,
    }


def build_filter_join_section(window, frame, config, all_fields, current_fields, start_row=4):
    join_frame = ttk.LabelFrame(frame, text="3. 多表匹配规则（没有副表时可不填；有副表时建议至少添加一条匹配规则）", padding=6)
    join_frame.grid(row=start_row, column=0, columnspan=8, sticky="nsew", pady=6)
    join_input_state = build_filter_join_input_state(current_fields, all_fields)
    left_var = tk.StringVar(value=join_input_state["left_default"])
    join_op_var = tk.StringVar(value="等于")
    right_var = tk.StringVar(value=join_input_state["right_default"])
    join_ops = ["等于", "不等于", "左包含右", "右包含左", "双向包含"]

    ttk.Label(join_frame, text="匹配关系：").grid(row=0, column=0, padx=4, pady=(4, 0), sticky=tk.W)
    ttk.Label(join_frame, text="左字段：").grid(row=0, column=1, padx=4, pady=(4, 0), sticky=tk.W)
    ttk.Label(join_frame, text="匹配：").grid(row=0, column=2, padx=4, pady=(4, 0), sticky=tk.W)
    ttk.Label(join_frame, text="右字段：").grid(row=0, column=3, padx=4, pady=(4, 0), sticky=tk.W)

    join_logic_var = tk.StringVar(value=config.get("join_logic", "AND"))
    ttk.Combobox(join_frame, textvariable=join_logic_var, values=window.LOGIC_TYPES, width=8, state="readonly").grid(row=1, column=0, padx=4, pady=4, sticky=tk.W)
    window.sync_var_to_config(join_logic_var, config, "join_logic")
    left_combo = ttk.Combobox(join_frame, textvariable=left_var, values=all_fields, width=28, state="normal")
    left_combo.grid(row=1, column=1, padx=4, pady=4)
    ttk.Combobox(join_frame, textvariable=join_op_var, values=join_ops, width=12, state="readonly").grid(row=1, column=2, padx=4, pady=4)
    right_combo = ttk.Combobox(join_frame, textvariable=right_var, values=all_fields, width=28, state="normal")
    right_combo.grid(row=1, column=3, padx=4, pady=4)
    ttk.Label(join_frame, text="AND=全部规则满足；OR=任意规则满足。", foreground="gray").grid(row=1, column=5, sticky=tk.W, padx=4, pady=4)

    join_tree = ttk.Treeview(join_frame, columns=("左字段", "匹配", "右字段"), show="headings", height=6)
    for column, width in [("左字段", 260), ("匹配", 120), ("右字段", 260)]:
        join_tree.heading(column, text=column)
        join_tree.column(column, width=width, anchor=tk.W)
    join_y_scroll = ttk.Scrollbar(join_frame, orient=tk.VERTICAL, command=join_tree.yview)
    join_x_scroll = ttk.Scrollbar(join_frame, orient=tk.HORIZONTAL, command=join_tree.xview)
    join_tree.configure(yscrollcommand=join_y_scroll.set, xscrollcommand=join_x_scroll.set)
    join_tree.grid(row=2, column=0, columnspan=6, sticky="nsew", padx=4, pady=4)
    join_y_scroll.grid(row=2, column=6, sticky="ns", pady=4)
    join_x_scroll.grid(row=3, column=0, columnspan=6, sticky="ew", padx=4)
    join_frame.rowconfigure(2, weight=1)
    join_frame.columnconfigure(5, weight=1)
    for row_values in filter_join_rules_to_rows(config.get("join_rules", [])):
        join_tree.insert("", tk.END, values=row_values)

    return {
        "frame": join_frame,
        "join_logic_var": join_logic_var,
        "left_var": left_var,
        "left_combo": left_combo,
        "join_op_var": join_op_var,
        "right_var": right_var,
        "right_combo": right_combo,
        "join_tree": join_tree,
        "button_row": 4,
    }


def build_filter_output_section(window, frame, config, all_fields, start_row=5):
    output_frame = ttk.LabelFrame(frame, text="4. 输出字段（不选择则输出全部可用字段）", padding=6)
    output_frame.grid(row=start_row, column=0, columnspan=8, sticky="nsew", pady=6)
    out_wrap = ttk.Frame(output_frame)
    out_wrap.pack(fill=tk.BOTH, expand=True)
    out_list = tk.Listbox(out_wrap, selectmode=tk.MULTIPLE, height=9, exportselection=False)
    out_scroll = ttk.Scrollbar(out_wrap, orient=tk.VERTICAL, command=out_list.yview)
    out_list.configure(yscrollcommand=out_scroll.set)
    out_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    out_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    selected = set(config.get("output_fields", []))
    for index, header in enumerate(all_fields):
        out_list.insert(tk.END, header)
        if header in selected:
            out_list.selection_set(index)
    actual_output_var = tk.StringVar(value="")
    ttk.Label(
        output_frame,
        textvariable=actual_output_var,
        foreground="gray",
        wraplength=1000,
    ).pack(fill=tk.X, pady=(4, 0))
    btns = ttk.Frame(output_frame)
    btns.pack(fill=tk.X, pady=4)
    return {
        "frame": output_frame,
        "out_list": out_list,
        "actual_output_var": actual_output_var,
        "button_frame": btns,
    }


def refresh_filter_risk_text(window, headers, config, risk_var, risk_label):
    warnings = window.get_plan_filter_config_warnings(
        headers,
        config.get("extra_tables", []),
        config.get("conditions", []),
        config.get("join_rules", []),
        config.get("join_logic", "AND"),
    )
    display = build_filter_risk_display_state(warnings)
    risk_var.set(display["text"])
    risk_label.configure(foreground=display["foreground"])


def refresh_filter_condition_value_input(field_state, value_source_var, value_var, value_combo):
    state = build_filter_condition_input_state(
        field_state["all_values"],
        value_source=value_source_var.get(),
        current_value=value_var.get(),
    )
    if value_source_var.get() != state["value_source"]:
        value_source_var.set(state["value_source"])
        return
    value_combo.configure(values=state["value_choices"])
    if value_var.get() != state["value_default"]:
        value_var.set(state["value_default"])


def filter_tree_rows(tree):
    return [tree.item(iid, "values") for iid in tree.get_children()]


def replace_filter_tree_rows(tree, rows):
    tree.delete(*tree.get_children())
    for row_values in rows:
        tree.insert("", tk.END, values=row_values)


def edit_filter_condition_cell(event, cond_tree, cond_edit_mode, sync_conditions_from_tree):
    if not cond_edit_mode.get():
        return
    region = cond_tree.identify("region", event.x, event.y)
    if region != "cell":
        return
    row_id = cond_tree.identify_row(event.y)
    col_id = cond_tree.identify_column(event.x)
    if not row_id or not col_id:
        return
    bbox = cond_tree.bbox(row_id, col_id)
    if not bbox:
        return
    x, y, width, height = bbox
    edit_state = build_treeview_cell_edit_state(cond_tree.item(row_id, "values"), col_id, 4)
    if edit_state is None:
        return
    col_index = edit_state["column_index"]
    values = edit_state["values"]
    entry = ttk.Entry(cond_tree)
    entry.place(x=x, y=y, width=width, height=height)
    entry.insert(0, edit_state["text"])
    entry.select_range(0, tk.END)
    entry.focus()
    closed = {"done": False}

    def close_editor(save=True):
        if closed["done"]:
            return
        closed["done"] = True
        if save:
            new_values = apply_treeview_cell_edit(values, col_index, entry.get(), 4)
            if new_values is not None:
                cond_tree.item(row_id, values=new_values)
                sync_conditions_from_tree()
        entry.destroy()

    entry.bind("<Return>", lambda e: close_editor(True))
    entry.bind("<Escape>", lambda e: close_editor(False))
    entry.bind("<FocusOut>", lambda e: close_editor(True))


def _first_service_issue_message(result, default="操作失败。"):
    for issue in result.get("issues") or []:
        message = issue.get("message")
        if message:
            return message
    return default


def build_filter_condition_action_buttons(window, condition_section, config, headers, field_state, refresh_filter_risk_text_callback):
    condition_frame = condition_section["frame"]
    cond_tree = condition_section["cond_tree"]
    cond_edit_mode = condition_section["cond_edit_mode"]
    field_var = condition_section["field_var"]
    op_var = condition_section["op_var"]
    value_source_var = condition_section["value_source_var"]
    value_var = condition_section["value_var"]

    def sync_conditions_from_tree():
        config["conditions"] = filter_conditions_from_rows(filter_tree_rows(cond_tree))
        refresh_filter_risk_text_callback()

    def add_cond():
        if not field_var.get().strip():
            messagebox.showwarning("提示", "请选择条件字段。")
            return
        result = append_filter_condition_row_via_service(
            filter_tree_rows(cond_tree),
            config,
            headers,
            field_state.get("all_values", []),
            field_var.get(),
            op_var.get(),
            value_source_var.get(),
            value_var.get(),
        )
        if not result["ok"]:
            messagebox.showwarning("提示", _first_service_issue_message(result))
            return
        replace_filter_tree_rows(cond_tree, result["rows"])
        sync_conditions_from_tree()

    def del_cond():
        selected = [cond_tree.index(iid) for iid in cond_tree.selection()]
        result = delete_filter_condition_rows_via_service(
            filter_tree_rows(cond_tree),
            config,
            headers,
            field_state.get("all_values", []),
            selected,
        )
        if not result["ok"]:
            messagebox.showwarning("提示", _first_service_issue_message(result))
            return
        replace_filter_tree_rows(cond_tree, result["rows"])
        sync_conditions_from_tree()

    cond_tree.bind(
        "<Double-1>",
        lambda event: edit_filter_condition_cell(event, cond_tree, cond_edit_mode, sync_conditions_from_tree),
    )
    ttk.Button(condition_frame, text="添加条件", command=add_cond).grid(row=condition_section["button_row"], column=1, padx=4, pady=4)
    ttk.Button(condition_frame, text="删除条件", command=del_cond).grid(row=condition_section["button_row"], column=2, padx=4, pady=4)
    return {
        "sync_conditions_from_tree": sync_conditions_from_tree,
    }


def build_filter_join_action_buttons(window, join_section, config, headers, field_state, refresh_filter_risk_text_callback):
    join_frame = join_section["frame"]
    left_var = join_section["left_var"]
    join_op_var = join_section["join_op_var"]
    right_var = join_section["right_var"]
    join_tree = join_section["join_tree"]

    def sync_join_rules_from_tree():
        config["join_rules"] = filter_join_rules_from_rows(filter_tree_rows(join_tree))
        refresh_filter_risk_text_callback()

    def add_join():
        if not left_var.get().strip() or not right_var.get().strip():
            messagebox.showwarning("提示", "请选择左右匹配字段。")
            return
        result = append_filter_join_rule_row_via_service(
            filter_tree_rows(join_tree),
            config,
            headers,
            field_state.get("all_values", []),
            left_var.get(),
            join_op_var.get(),
            right_var.get(),
        )
        if not result["ok"]:
            messagebox.showwarning("提示", _first_service_issue_message(result))
            return
        replace_filter_tree_rows(join_tree, result["rows"])
        sync_join_rules_from_tree()

    def del_join():
        selected = [join_tree.index(iid) for iid in join_tree.selection()]
        result = delete_filter_join_rule_rows_via_service(
            filter_tree_rows(join_tree),
            config,
            headers,
            field_state.get("all_values", []),
            selected,
        )
        if not result["ok"]:
            messagebox.showwarning("提示", _first_service_issue_message(result))
            return
        replace_filter_tree_rows(join_tree, result["rows"])
        sync_join_rules_from_tree()

    ttk.Button(join_frame, text="添加匹配规则", command=add_join).grid(row=join_section["button_row"], column=1, padx=4, pady=4)
    ttk.Button(join_frame, text="删除匹配规则", command=del_join).grid(row=join_section["button_row"], column=2, padx=4, pady=4)
    return {
        "sync_join_rules_from_tree": sync_join_rules_from_tree,
    }


def refresh_filter_actual_output_text(out_list, actual_output_var, headers, field_state, config):
    selected_fields = [out_list.get(index) for index in out_list.curselection()]
    actual_output_var.set(build_filter_actual_output_text(
        selected_fields,
        headers,
        field_state["all_values"],
        config.get("extra_tables", []),
    ))


def sync_filter_output_fields(out_list, actual_output_var, headers, field_state, config):
    config["output_fields"] = [out_list.get(index) for index in out_list.curselection()]
    refresh_filter_actual_output_text(out_list, actual_output_var, headers, field_state, config)


def build_filter_output_action_buttons(window, output_section, config, headers, field_state):
    out_list = output_section["out_list"]
    actual_output_var = output_section["actual_output_var"]

    def refresh_actual_output_text():
        refresh_filter_actual_output_text(out_list, actual_output_var, headers, field_state, config)

    def sync_output_fields():
        sync_filter_output_fields(out_list, actual_output_var, headers, field_state, config)

    out_list.bind("<<ListboxSelect>>", lambda e: sync_output_fields())
    btns = output_section["button_frame"]
    ttk.Button(
        btns,
        text="选择全部输出字段",
        command=lambda: (select_all_output_fields(out_list, config), refresh_actual_output_text()),
    ).pack(side=tk.LEFT, padx=2)
    ttk.Button(
        btns,
        text="反选",
        command=lambda: (invert_output_fields(out_list, config), refresh_actual_output_text()),
    ).pack(side=tk.LEFT, padx=2)
    ttk.Button(
        btns,
        text="只选当前表字段",
        command=lambda: (select_current_table_output_fields(out_list, config), refresh_actual_output_text()),
    ).pack(side=tk.LEFT, padx=2)
    ttk.Button(btns, text="清空输出选择", command=lambda: (out_list.selection_clear(0, tk.END), sync_output_fields())).pack(side=tk.LEFT, padx=2)

    dedupe_text = tk.StringVar(value=filter_dedupe_button_text(config.get("remove_duplicates", False)))

    def toggle_filter_dedupe():
        enabled = toggle_filter_dedupe_config(config)
        dedupe_text.set(filter_dedupe_button_text(enabled))

    ttk.Button(btns, textvariable=dedupe_text, command=toggle_filter_dedupe).pack(side=tk.LEFT, padx=(12, 2))
    ttk.Label(btns, text="按最终输出整行去重，保留第一条。", foreground="gray").pack(side=tk.LEFT, padx=4)
    return {
        "refresh_actual_output_text": refresh_actual_output_text,
        "sync_output_fields": sync_output_fields,
    }


def refresh_filter_field_sources(
    window,
    headers,
    config,
    transit_context,
    field_state,
    source_section,
    condition_section,
    join_section,
    output_section,
    sync_output_fields,
    refresh_condition_value_input_callback,
    refresh_filter_risk_text_callback,
):
    table_list = source_section["table_list"]
    value_source_var = condition_section["value_source_var"]
    config["extra_tables"] = [table_list.get(index) for index in table_list.curselection()]
    available_fields = window.get_plan_filter_available_fields(headers, config.get("extra_tables", []), transit_context)
    state = build_filter_field_refresh_state(
        headers,
        available_fields,
        value_source_var.get(),
        config.get("output_fields", []),
    )
    field_state.clear()
    field_state.update(state)
    window.refresh_combo_values(
        condition_section["field_combo"],
        condition_section["field_var"],
        state["all_values"],
        keep_custom=False,
        fallback=state["first_any"],
    )
    window.refresh_combo_values(
        condition_section["value_combo"],
        condition_section["value_var"],
        state["value_choices"],
        keep_custom=state["value_source"] != "字段值",
        fallback=state["value_fallback"],
    )
    window.refresh_combo_values(
        join_section["left_combo"],
        join_section["left_var"],
        state["all_values"],
        keep_custom=False,
        fallback=state["first_current"],
    )
    window.refresh_combo_values(
        join_section["right_combo"],
        join_section["right_var"],
        state["all_values"],
        keep_custom=False,
        fallback=state["first_external"],
    )
    window.refresh_listbox_values(
        output_section["out_list"],
        state["all_values"],
        state["selected_output"],
    )
    sync_output_fields()
    refresh_condition_value_input_callback()
    refresh_filter_risk_text_callback()
    window.status_var.set(build_filter_field_refresh_status(len(config.get("extra_tables", [])), len(state["all_values"])))


def build_filter_config(window, config, headers, transit_context=None):
    """
    计划节点内的高级筛选配置。
    主输入固定为“上一步结果”，在字段列表中显示为“当前表.字段”。
    可额外勾选 SQLite 数据库中的表，并通过匹配规则把当前表和副表关联起来。
    """
    ensure_filter_config_defaults(config)
    window.normalize_plan_filter_config_field_references(
        config,
        headers,
        config.get("extra_tables", []),
    )

    frame = ttk.LabelFrame(window.config_frame, text="高级筛选节点（支持：上一步结果 + 多表匹配）", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)

    risk_section = build_filter_header_risk_section(window, frame, start_row=0)
    risk_var = risk_section["risk_var"]
    risk_label = risk_section["risk_label"]

    def refresh_risk_text_callback():
        refresh_filter_risk_text(window, headers, config, risk_var, risk_label)

    selected_tables = list(config.get("extra_tables", []))
    transit_context = transit_context or {"transit_tables": {}}
    all_fields = window.get_plan_filter_available_fields(headers, selected_tables, transit_context)
    field_state = build_filter_field_refresh_state(
        headers,
        all_fields,
        selected_output_fields=config.get("output_fields", []),
    )
    current_fields = field_state["current_values"]

    def sync_extra_tables(rebuild=False):
        config["extra_tables"] = [table_list.get(index) for index in table_list.curselection()]
        if rebuild:
            refresh_field_sources_callback()

    source_section = build_filter_source_table_section(
        window,
        frame,
        config,
        headers,
        selected_tables,
        transit_context,
        sync_extra_tables,
        start_row=risk_section["next_row"],
    )
    table_list = source_section["table_list"]

    condition_section = build_filter_condition_section(window, frame, config, all_fields, start_row=3)
    value_source_var = condition_section["value_source_var"]
    value_var = condition_section["value_var"]
    value_combo = condition_section["value_combo"]

    def refresh_condition_value_input(*_):
        refresh_filter_condition_value_input(field_state, value_source_var, value_var, value_combo)

    value_source_var.trace_add("write", refresh_condition_value_input)
    refresh_condition_value_input()

    build_filter_condition_action_buttons(window, condition_section, config, headers, field_state, refresh_risk_text_callback)

    join_section = build_filter_join_section(window, frame, config, all_fields, current_fields, start_row=4)
    join_logic_var = join_section["join_logic_var"]
    join_logic_var.trace_add("write", lambda *_: refresh_risk_text_callback())
    build_filter_join_action_buttons(window, join_section, config, headers, field_state, refresh_risk_text_callback)

    output_section = build_filter_output_section(window, frame, config, all_fields, start_row=5)
    output_actions = build_filter_output_action_buttons(window, output_section, config, headers, field_state)
    refresh_actual_output_text = output_actions["refresh_actual_output_text"]
    sync_output_fields = output_actions["sync_output_fields"]

    def refresh_field_sources_callback():
        refresh_filter_field_sources(
            window,
            headers,
            config,
            transit_context,
            field_state,
            source_section,
            condition_section,
            join_section,
            output_section,
            sync_output_fields,
            refresh_condition_value_input,
            refresh_risk_text_callback,
        )

    refresh_actual_output_text()
    refresh_risk_text_callback()


def select_all_output_fields(listbox, config):
    fields = select_all_filter_output_fields(listbox.get(0, tk.END))
    listbox.selection_set(0, tk.END)
    config["output_fields"] = fields


def invert_output_fields(listbox, config):
    selected = set(listbox.curselection())
    fields = list(listbox.get(0, tk.END))
    result = invert_filter_output_fields_by_indexes(fields, selected)
    listbox.selection_clear(0, tk.END)
    for index, field in enumerate(fields):
        if index not in selected:
            listbox.selection_set(index)
    config["output_fields"] = result


def select_current_table_output_fields(listbox, config):
    listbox.selection_clear(0, tk.END)
    fields = list(listbox.get(0, tk.END))
    selected = select_current_table_filter_output_fields(fields)
    selected_set = set(selected)
    for index, field in enumerate(fields):
        if field in selected_set:
            listbox.selection_set(index)
    config["output_fields"] = selected
