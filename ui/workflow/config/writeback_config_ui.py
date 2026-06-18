# -*- coding: utf-8 -*-
"""Tkinter UI helpers for the writeback workflow node configuration."""

import tkinter as tk
from tkinter import ttk, messagebox


def build_writeback_header_section(frame):
    ttk.Label(
        frame,
        text=(
            "说明：本节点支持两个方向。1）当前表写入 SQLite 目标表：按匹配/行号把当前工作流数据写入指定数据库表；"
            "2）其他表写入当前表：读取 SQLite 其他表数据，按匹配/行号写入当前工作流表，可覆盖已有字段，也可输入新字段名生成新列。"
        ),
        foreground="gray",
        wraplength=1080,
    ).grid(row=0, column=0, columnspan=10, sticky=tk.W, padx=4, pady=(0, 6))


def build_writeback_source_section(window, frame, config, headers, table_names, external_columns, direction_values):
    direction_var, direction_combo = window.add_labeled_combo_control(
        frame,
        "写入方向：",
        config.get("writeback_direction", direction_values[0]),
        direction_values,
        1,
        0,
        24,
    )
    window.sync_var_to_config(direction_var, config, "writeback_direction")

    direction = direction_var.get()
    external_key = "target_table" if direction == "当前表写入SQLite目标表" else "source_table"
    external_label = "目标表：" if direction == "当前表写入SQLite目标表" else "来源表："
    external_label_widget = ttk.Label(frame, text=external_label)
    external_label_widget.grid(row=1, column=2, sticky=tk.W, padx=4, pady=4)
    external_table_var = tk.StringVar(value=config.get(external_key, ""))
    external_table_combo = ttk.Combobox(frame, textvariable=external_table_var, values=table_names, width=32, state="readonly")
    external_table_combo.grid(row=1, column=3, sticky=tk.W, padx=4, pady=4)

    refresh_button = ttk.Button(frame, text="刷新表/字段")
    refresh_button.grid(row=1, column=4, sticky=tk.W, padx=4, pady=4)
    if direction == "当前表写入SQLite目标表":
        count_text = f"当前来源字段：{len(headers)} 个；SQLite目标字段：{len(external_columns)} 个"
    else:
        count_text = f"SQLite来源字段：{len(external_columns)} 个；当前目标字段：{len(headers)} 个（目标字段可手动输入新字段名）"
    count_label = ttk.Label(frame, text=count_text, foreground="gray")
    count_label.grid(row=1, column=5, columnspan=4, sticky=tk.W, padx=4, pady=4)

    use_match_var = tk.BooleanVar(value=bool(config.get("use_match_rules", True)))
    ttk.Checkbutton(frame, text="启用匹配规则定位对应行", variable=use_match_var).grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=4, pady=4)
    window.sync_bool_to_config(use_match_var, config, "use_match_rules")

    insert_missing_var = tk.BooleanVar(value=bool(config.get("sequential_insert_missing_rows", True)))
    if direction == "当前表写入SQLite目标表":
        insert_text = "关闭匹配时：目标行不足则按来源完整结构新增行"
    else:
        insert_text = "关闭匹配时：来源行多于当前表时自动新增当前行"
    insert_missing_cb = ttk.Checkbutton(frame, text=insert_text, variable=insert_missing_var)
    insert_missing_cb.grid(row=2, column=2, columnspan=4, sticky=tk.W, padx=4, pady=4)
    window.sync_bool_to_config(insert_missing_var, config, "sequential_insert_missing_rows")

    write_range_values = ["局部覆盖，保留目标原行数", "清空目标字段后覆盖，保留目标原行数", "按来源完整结构覆盖"]
    if config.get("write_range_mode") not in write_range_values:
        config["write_range_mode"] = "局部覆盖，保留目标原行数"
    write_range_var = window.add_labeled_combo(
        frame,
        "写入范围：",
        config.get("write_range_mode", "局部覆盖，保留目标原行数"),
        write_range_values,
        2,
        6,
        30,
    )
    window.sync_var_to_config(write_range_var, config, "write_range_mode")
    return {
        "direction_var": direction_var,
        "direction_combo": direction_combo,
        "refresh_button": refresh_button,
        "external_label_widget": external_label_widget,
        "external_table_var": external_table_var,
        "external_table_combo": external_table_combo,
        "count_label": count_label,
        "use_match_var": use_match_var,
        "insert_missing_var": insert_missing_var,
        "insert_missing_cb": insert_missing_cb,
        "write_range_var": write_range_var,
        "write_range_values": write_range_values,
    }


def build_writeback_match_section(frame, config, headers, external_columns):
    match_frame_title = "1. 匹配规则（当前表字段 ↔ 外部表字段；可关闭后按行号顺序对应）"
    match_frame = ttk.LabelFrame(frame, text=match_frame_title, padding=6)
    match_frame.grid(row=3, column=0, columnspan=10, sticky="nsew", padx=4, pady=6)
    src_match_var = tk.StringVar(value=headers[0] if headers else "")
    op_var = tk.StringVar(value="等于")
    tgt_match_var = tk.StringVar(value=external_columns[0] if external_columns else "")
    ttk.Label(match_frame, text="当前表字段：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
    src_match_combo = ttk.Combobox(match_frame, textvariable=src_match_var, values=headers, width=24, state="normal")
    src_match_combo.grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
    ttk.Label(match_frame, text="匹配方式：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
    ttk.Combobox(match_frame, textvariable=op_var, values=["等于", "不等于", "当前包含外部", "外部包含当前", "双向包含"], width=14, state="readonly").grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)
    ttk.Label(match_frame, text="外部表字段：").grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
    tgt_match_combo = ttk.Combobox(match_frame, textvariable=tgt_match_var, values=external_columns, width=24, state="normal")
    tgt_match_combo.grid(row=0, column=5, sticky=tk.W, padx=4, pady=4)

    match_tree = ttk.Treeview(match_frame, columns=("当前表字段", "匹配方式", "外部表字段"), show="headings", height=4)
    for col, width in [("当前表字段", 220), ("匹配方式", 120), ("外部表字段", 220)]:
        match_tree.heading(col, text=col)
        match_tree.column(col, width=width, anchor=tk.W)
    match_y = ttk.Scrollbar(match_frame, orient=tk.VERTICAL, command=match_tree.yview)
    match_x = ttk.Scrollbar(match_frame, orient=tk.HORIZONTAL, command=match_tree.xview)
    match_tree.configure(yscrollcommand=match_y.set, xscrollcommand=match_x.set)
    match_tree.grid(row=1, column=0, columnspan=6, sticky="nsew", padx=4, pady=4)
    match_y.grid(row=1, column=6, sticky="ns", pady=4)
    match_x.grid(row=2, column=0, columnspan=6, sticky="ew", padx=4)
    for rule in config.get("match_rules", []):
        match_tree.insert("", tk.END, values=(rule.get("source_field", ""), rule.get("operator", "等于"), rule.get("target_field", "")))
    return {
        "frame": match_frame,
        "src_match_var": src_match_var,
        "src_match_combo": src_match_combo,
        "op_var": op_var,
        "tgt_match_var": tgt_match_var,
        "tgt_match_combo": tgt_match_combo,
        "match_tree": match_tree,
    }


def build_writeback_mapping_section(frame, config, headers, external_columns, direction):
    if direction == "当前表写入SQLite目标表":
        mapping_title = "2. 字段映射规则（当前表字段 → SQLite目标表字段）"
        left_label, right_label = "当前表字段：", "写入目标字段："
        left_values, right_values = headers, external_columns
        left_default = headers[0] if headers else ""
        right_default = external_columns[0] if external_columns else ""
    else:
        mapping_title = "2. 字段映射规则（SQLite来源表字段 → 当前表字段 / 新字段名）"
        left_label, right_label = "来源表字段：", "写入当前字段："
        left_values, right_values = external_columns, headers
        left_default = external_columns[0] if external_columns else ""
        right_default = headers[0] if headers else "新字段"

    mapping_frame = ttk.LabelFrame(frame, text=mapping_title, padding=6)
    mapping_frame.grid(row=4, column=0, columnspan=10, sticky="nsew", padx=4, pady=6)
    src_map_var = tk.StringVar(value=left_default)
    tgt_map_var = tk.StringVar(value=right_default)
    src_map_label = ttk.Label(mapping_frame, text=left_label)
    src_map_label.grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
    src_map_combo = ttk.Combobox(mapping_frame, textvariable=src_map_var, values=left_values, width=24, state="normal")
    src_map_combo.grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
    tgt_map_label = ttk.Label(mapping_frame, text=right_label)
    tgt_map_label.grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
    tgt_map_combo = ttk.Combobox(mapping_frame, textvariable=tgt_map_var, values=right_values, width=24, state="normal")
    tgt_map_combo.grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)
    ttk.Label(mapping_frame, text="提示：右侧字段可手动输入新字段名。", foreground="gray").grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)

    mapping_tree = ttk.Treeview(mapping_frame, columns=("来源字段", "写入字段"), show="headings", height=5)
    for col, width in [("来源字段", 260), ("写入字段", 260)]:
        mapping_tree.heading(col, text=col)
        mapping_tree.column(col, width=width, anchor=tk.W)
    mapping_y = ttk.Scrollbar(mapping_frame, orient=tk.VERTICAL, command=mapping_tree.yview)
    mapping_x = ttk.Scrollbar(mapping_frame, orient=tk.HORIZONTAL, command=mapping_tree.xview)
    mapping_tree.configure(yscrollcommand=mapping_y.set, xscrollcommand=mapping_x.set)
    mapping_tree.grid(row=1, column=0, columnspan=4, sticky="nsew", padx=4, pady=4)
    mapping_y.grid(row=1, column=4, sticky="ns", pady=4)
    mapping_x.grid(row=2, column=0, columnspan=4, sticky="ew", padx=4)
    for item in config.get("field_mappings", []):
        mapping_tree.insert("", tk.END, values=(item.get("source_field", ""), item.get("target_field", "")))
    return {
        "frame": mapping_frame,
        "src_map_var": src_map_var,
        "src_map_label": src_map_label,
        "src_map_combo": src_map_combo,
        "tgt_map_var": tgt_map_var,
        "tgt_map_label": tgt_map_label,
        "tgt_map_combo": tgt_map_combo,
        "mapping_tree": mapping_tree,
        "left_values": left_values,
        "right_values": right_values,
    }


def build_writeback_policy_section(window, frame, config):
    policy_frame = ttk.LabelFrame(frame, text="3. 写入策略与安全设置", padding=6)
    policy_frame.grid(row=5, column=0, columnspan=10, sticky="nsew", padx=4, pady=6)
    overwrite_var = window.add_labeled_combo(policy_frame, "覆盖策略：", config.get("overwrite_policy", "目标已有值且不同才覆盖"), ["覆盖全部", "只覆盖目标为空的字段", "目标已有值则跳过", "目标已有值且不同才覆盖"], 0, 0, 22)
    empty_var = window.add_labeled_combo(policy_frame, "来源为空：", config.get("source_empty_policy", "跳过"), ["跳过", "写入空值", "写入固定值"], 0, 2, 16)
    empty_fixed_var = window.add_labeled_entry(policy_frame, "固定值：", config.get("source_empty_fixed", ""), 0, 4, 18)
    no_match_var = window.add_labeled_combo(policy_frame, "未匹配：", config.get("no_match_policy", "跳过并记录"), ["跳过并记录"], 1, 0, 16)
    multi_match_var = window.add_labeled_combo(policy_frame, "多匹配：", config.get("multi_match_policy", "跳过并记录"), ["跳过并记录", "只更新第一行", "全部更新"], 1, 2, 16)
    duplicate_var = window.add_labeled_combo(policy_frame, "重复目标：", config.get("duplicate_target_policy", "跳过重复并记录异常"), ["跳过重复并记录异常", "第一个有效", "后面的覆盖前面的"], 1, 4, 20)
    window.sync_var_to_config(overwrite_var, config, "overwrite_policy")
    window.sync_var_to_config(empty_var, config, "source_empty_policy")
    window.sync_var_to_config(empty_fixed_var, config, "source_empty_fixed")
    window.sync_var_to_config(no_match_var, config, "no_match_policy")
    window.sync_var_to_config(multi_match_var, config, "multi_match_policy")
    window.sync_var_to_config(duplicate_var, config, "duplicate_target_policy")

    enable_write_var = tk.BooleanVar(value=bool(config.get("enable_write", False)))
    backup_var = tk.BooleanVar(value=bool(config.get("backup_before_write", True)))
    output_preview_var = tk.BooleanVar(value=bool(config.get("output_preview_table", True)))
    enable_write_cb = ttk.Checkbutton(policy_frame, text="允许正式执行时写入 SQLite 目标表", variable=enable_write_var)
    backup_cb = ttk.Checkbutton(policy_frame, text="写入前自动备份目标表", variable=backup_var)
    output_preview_cb = ttk.Checkbutton(policy_frame, text="节点输出写入预览表", variable=output_preview_var)
    policy_note_label = ttk.Label(policy_frame, text="", foreground="gray")
    window.sync_bool_to_config(enable_write_var, config, "enable_write")
    window.sync_bool_to_config(backup_var, config, "backup_before_write")
    window.sync_bool_to_config(output_preview_var, config, "output_preview_table")
    return {
        "frame": policy_frame,
        "enable_write_cb": enable_write_cb,
        "backup_cb": backup_cb,
        "output_preview_cb": output_preview_cb,
        "policy_note_label": policy_note_label,
    }


def sync_writeback_match_rules(match_section, config):
    config["match_rules"] = []
    match_tree = match_section["match_tree"]
    for iid in match_tree.get_children():
        source_field, operator, target_field = match_tree.item(iid, "values")
        config["match_rules"].append({"source_field": source_field, "operator": operator, "target_field": target_field})


def build_writeback_match_action_buttons(match_section, config):
    match_frame = match_section["frame"]
    src_match_var = match_section["src_match_var"]
    op_var = match_section["op_var"]
    tgt_match_var = match_section["tgt_match_var"]
    match_tree = match_section["match_tree"]

    def add_match_rule():
        if not src_match_var.get() or not tgt_match_var.get():
            messagebox.showwarning("提示", "请选择当前表字段和外部表字段。")
            return
        match_tree.insert("", tk.END, values=(src_match_var.get(), op_var.get(), tgt_match_var.get()))
        sync_writeback_match_rules(match_section, config)

    def del_match_rule():
        for iid in match_tree.selection():
            match_tree.delete(iid)
        sync_writeback_match_rules(match_section, config)

    ttk.Button(match_frame, text="添加匹配规则", command=add_match_rule).grid(row=0, column=7, sticky=tk.W, padx=4, pady=4)
    ttk.Button(match_frame, text="删除选中规则", command=del_match_rule).grid(row=1, column=7, sticky=tk.NW, padx=4, pady=4)


def sync_writeback_mappings(mapping_section, config):
    config["field_mappings"] = []
    mapping_tree = mapping_section["mapping_tree"]
    for iid in mapping_tree.get_children():
        source_field, target_field = mapping_tree.item(iid, "values")
        config["field_mappings"].append({"source_field": source_field, "target_field": target_field})


def build_writeback_mapping_action_buttons(mapping_section, config, writeback_field_state):
    mapping_frame = mapping_section["frame"]
    src_map_var = mapping_section["src_map_var"]
    tgt_map_var = mapping_section["tgt_map_var"]
    mapping_tree = mapping_section["mapping_tree"]

    def add_mapping():
        if not src_map_var.get() or not tgt_map_var.get():
            messagebox.showwarning("提示", "请选择/填写映射字段。")
            return
        mapping_tree.insert("", tk.END, values=(src_map_var.get(), tgt_map_var.get()))
        sync_writeback_mappings(mapping_section, config)

    def del_mapping():
        for iid in mapping_tree.selection():
            mapping_tree.delete(iid)
        sync_writeback_mappings(mapping_section, config)

    def auto_same_name_mapping():
        for iid in mapping_tree.get_children():
            mapping_tree.delete(iid)
        common = [h for h in writeback_field_state.get("left_values", []) if h in writeback_field_state.get("right_values", [])]
        for h in common:
            mapping_tree.insert("", tk.END, values=(h, h))
        sync_writeback_mappings(mapping_section, config)

    ttk.Button(mapping_frame, text="添加映射", command=add_mapping).grid(row=0, column=5, sticky=tk.W, padx=4, pady=4)
    ttk.Button(mapping_frame, text="删除映射", command=del_mapping).grid(row=1, column=5, sticky=tk.NW, padx=4, pady=4)
    ttk.Button(mapping_frame, text="同名字段自动映射", command=auto_same_name_mapping).grid(row=1, column=6, sticky=tk.NW, padx=4, pady=4)


def refresh_writeback_policy_widgets(direction_var, policy_section):
    enable_write_cb = policy_section["enable_write_cb"]
    backup_cb = policy_section["backup_cb"]
    output_preview_cb = policy_section["output_preview_cb"]
    policy_note_label = policy_section["policy_note_label"]
    if direction_var.get() == "当前表写入SQLite目标表":
        enable_write_cb.grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=4, pady=4)
        backup_cb.grid(row=2, column=2, columnspan=2, sticky=tk.W, padx=4, pady=4)
        output_preview_cb.grid(row=2, column=4, columnspan=2, sticky=tk.W, padx=4, pady=4)
        policy_note_label.configure(text="安全提示：预览计划不会写库；正式执行时也必须勾选允许写入才会 UPDATE/INSERT。")
        policy_note_label.grid(row=3, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(6, 0))
    else:
        enable_write_cb.grid_remove()
        backup_cb.grid_remove()
        output_preview_cb.grid_remove()
        policy_note_label.configure(text="当前模式会把来源表数据写入工作流当前表，只修改内存中的当前结果；不会直接修改 SQLite。右侧映射字段可输入新字段名。")
        policy_note_label.grid(row=2, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(6, 0))


def writeback_external_key(direction):
    return "target_table" if direction == "当前表写入SQLite目标表" else "source_table"


def refresh_writeback_fields(
    window,
    headers,
    config,
    direction_values,
    table_names,
    source_section,
    match_section,
    mapping_section,
    policy_section,
    writeback_field_state,
    last_writeback_direction,
    refresh_tables=False,
):
    direction_var = source_section["direction_var"]
    external_table_var = source_section["external_table_var"]
    external_table_combo = source_section["external_table_combo"]
    external_label_widget = source_section["external_label_widget"]
    count_label = source_section["count_label"]
    insert_missing_cb = source_section["insert_missing_cb"]

    if refresh_tables:
        try:
            table_names[:] = window.app.get_table_names()
        except Exception:
            table_names[:] = window.get_sqlite_table_names()
        window.refresh_combo_values(
            external_table_combo,
            external_table_var,
            table_names,
            keep_custom=False,
            fallback=table_names[0] if table_names else "",
        )

    cur_direction = direction_var.get() or direction_values[0]
    direction_changed = cur_direction != last_writeback_direction["value"]
    cur_external_key = writeback_external_key(cur_direction)
    if direction_changed:
        desired_table = config.get(cur_external_key, "") or (table_names[0] if table_names else "")
        if desired_table not in table_names and table_names:
            desired_table = table_names[0]
        external_table_var.set(desired_table)

    config["writeback_direction"] = cur_direction
    config[cur_external_key] = external_table_var.get()
    external_label_widget.configure(text="目标表：" if cur_direction == "当前表写入SQLite目标表" else "来源表：")

    try:
        ext_columns = window.app.get_table_columns(external_table_var.get()) if external_table_var.get() else []
    except Exception:
        ext_columns = []
    writeback_field_state["external_columns"] = list(ext_columns)

    mapping_frame = mapping_section["frame"]
    src_map_label = mapping_section["src_map_label"]
    tgt_map_label = mapping_section["tgt_map_label"]
    if cur_direction == "当前表写入SQLite目标表":
        count_label.configure(text=f"当前来源字段：{len(headers)} 个；SQLite目标字段：{len(ext_columns)} 个")
        insert_missing_cb.configure(text="关闭匹配时：目标行不足则按来源完整结构新增行")
        mapping_frame.configure(text="2. 字段映射规则（当前表字段 → SQLite目标表字段）")
        src_map_label.configure(text="当前表字段：")
        tgt_map_label.configure(text="写入目标字段：")
        left_values = list(headers)
        right_values = list(ext_columns)
        src_fallback = headers[0] if headers else ""
        tgt_fallback = ext_columns[0] if ext_columns else ""
    else:
        count_label.configure(text=f"SQLite来源字段：{len(ext_columns)} 个；当前目标字段：{len(headers)} 个（目标字段可手动输入新字段名）")
        insert_missing_cb.configure(text="关闭匹配时：来源行多于当前表时自动新增当前行")
        mapping_frame.configure(text="2. 字段映射规则（SQLite来源表字段 → 当前表字段 / 新字段名）")
        src_map_label.configure(text="来源表字段：")
        tgt_map_label.configure(text="写入当前字段：")
        left_values = list(ext_columns)
        right_values = list(headers)
        src_fallback = ext_columns[0] if ext_columns else ""
        tgt_fallback = headers[0] if headers else "新字段"

    writeback_field_state["left_values"] = list(left_values)
    writeback_field_state["right_values"] = list(right_values)
    window.refresh_combo_values(
        match_section["src_match_combo"],
        match_section["src_match_var"],
        headers,
        keep_custom=True,
        fallback=headers[0] if headers else "",
    )
    window.refresh_combo_values(
        match_section["tgt_match_combo"],
        match_section["tgt_match_var"],
        ext_columns,
        keep_custom=True,
        fallback=ext_columns[0] if ext_columns else "",
    )
    window.refresh_combo_values(
        mapping_section["src_map_combo"],
        mapping_section["src_map_var"],
        left_values,
        keep_custom=True,
        fallback=src_fallback,
    )
    window.refresh_combo_values(
        mapping_section["tgt_map_combo"],
        mapping_section["tgt_map_var"],
        right_values,
        keep_custom=True,
        fallback=tgt_fallback,
    )
    refresh_writeback_policy_widgets(direction_var, policy_section)
    last_writeback_direction["value"] = cur_direction
    window.status_var.set(f"字段映射写入表字段已局部刷新：外部表 {external_table_var.get()}，{len(ext_columns)} 个字段。")


def build_writeback_config(window, config, headers):
    direction_values = ["当前表写入SQLite目标表", "其他表写入当前表"]
    config.setdefault("writeback_direction", direction_values[0])
    if config.get("writeback_direction") not in direction_values:
        config["writeback_direction"] = direction_values[0]
    config.setdefault("target_table", "")
    config.setdefault("source_table", config.get("target_table", ""))
    config.setdefault("use_match_rules", True)
    config.setdefault("match_rules", [])
    config.setdefault("field_mappings", [])
    config.setdefault("overwrite_policy", "目标已有值且不同才覆盖")
    config.setdefault("source_empty_policy", "跳过")
    config.setdefault("source_empty_fixed", "")
    config.setdefault("no_match_policy", "跳过并记录")
    config.setdefault("multi_match_policy", "跳过并记录")
    config.setdefault("duplicate_target_policy", "跳过重复并记录异常")
    config.setdefault("enable_write", False)
    config.setdefault("backup_before_write", True)
    config.setdefault("output_preview_table", True)
    config.setdefault("sequential_insert_missing_rows", True)
    config.setdefault("write_range_mode", "局部覆盖，保留目标原行数")

    frame = ttk.LabelFrame(window.config_frame, text="字段映射写入表节点（写回 / 写入当前表）", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    build_writeback_header_section(frame)

    try:
        table_names = window.app.get_table_names()
    except Exception:
        table_names = []
    if config.get("target_table") not in table_names and table_names:
        config["target_table"] = table_names[0]
    if config.get("source_table") not in table_names and table_names:
        config["source_table"] = config.get("target_table") or table_names[0]

    direction = config.get("writeback_direction", direction_values[0])
    external_key = writeback_external_key(direction)
    external_table_name = config.get(external_key, "")

    external_columns = []
    try:
        if external_table_name:
            external_columns = window.app.get_table_columns(external_table_name)
    except Exception:
        external_columns = []

    source_section = build_writeback_source_section(
        window,
        frame,
        config,
        headers,
        table_names,
        external_columns,
        direction_values,
    )
    direction_var = source_section["direction_var"]
    refresh_button = source_section["refresh_button"]
    external_table_var = source_section["external_table_var"]

    match_section = build_writeback_match_section(frame, config, headers, external_columns)
    build_writeback_match_action_buttons(match_section, config)

    mapping_section = build_writeback_mapping_section(frame, config, headers, external_columns, direction)
    writeback_field_state = {
        "external_columns": list(external_columns),
        "left_values": list(mapping_section["left_values"]),
        "right_values": list(mapping_section["right_values"]),
    }
    build_writeback_mapping_action_buttons(mapping_section, config, writeback_field_state)

    policy_section = build_writeback_policy_section(window, frame, config)
    refresh_writeback_policy_widgets(direction_var, policy_section)

    refreshing_writeback = {"active": False}
    last_writeback_direction = {"value": direction_var.get()}

    def refresh_fields(refresh_tables=False):
        if refreshing_writeback["active"]:
            return
        refreshing_writeback["active"] = True
        try:
            refresh_writeback_fields(
                window,
                headers,
                config,
                direction_values,
                table_names,
                source_section,
                match_section,
                mapping_section,
                policy_section,
                writeback_field_state,
                last_writeback_direction,
                refresh_tables=refresh_tables,
            )
        finally:
            refreshing_writeback["active"] = False

    def schedule_refresh(*_):
        window.window.after_idle(lambda: refresh_fields(False))

    refresh_button.configure(command=lambda: refresh_fields(True))
    direction_var.trace_add("write", schedule_refresh)
    external_table_var.trace_add("write", schedule_refresh)
