# -*- coding: utf-8 -*-
"""Tkinter UI helpers for the rename-columns workflow node configuration."""

import tkinter as tk
from tkinter import ttk, messagebox


RENAME_MODE_VALUES = ["手动映射改名", "批量添加前缀", "批量添加后缀", "批量替换字段名字符"]
DUPLICATE_POLICY_VALUES = ["自动追加编号", "报错并停止"]
MISSING_POLICY_VALUES = ["跳过并记录警告", "报错并停止"]
SCOPE_VALUES = ["全部字段", "选中字段"]


def build_rename_columns_general_section(window, frame, config):
    ttk.Label(
        frame,
        text="只修改当前工作流表的字段名，不修改数据内容。适合在工作流开头统一字段名，或在输出前整理字段名。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=0, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(0, 6))

    mode_var = window.add_labeled_combo(frame, "改名模式：", config.get("mode", "手动映射改名"), RENAME_MODE_VALUES, 1, 0, 18)
    duplicate_var = window.add_labeled_combo(frame, "重复字段处理：", config.get("duplicate_policy", "自动追加编号"), DUPLICATE_POLICY_VALUES, 1, 2, 18)
    missing_var = window.add_labeled_combo(frame, "字段不存在时：", config.get("missing_policy", "跳过并记录警告"), MISSING_POLICY_VALUES, 1, 4, 18)
    trim_var = tk.BooleanVar(value=bool(config.get("trim_names", True)))
    ttk.Checkbutton(frame, text="去除新字段名首尾空格", variable=trim_var).grid(row=1, column=6, sticky=tk.W, padx=4, pady=4)
    window.sync_var_to_config(mode_var, config, "mode")
    window.sync_var_to_config(duplicate_var, config, "duplicate_policy")
    window.sync_var_to_config(missing_var, config, "missing_policy")
    window.sync_bool_to_config(trim_var, config, "trim_names")
    return {
        "mode_var": mode_var,
        "duplicate_var": duplicate_var,
        "missing_var": missing_var,
        "trim_var": trim_var,
    }


def build_rename_columns_manual_section(frame, config, headers):
    manual_frame = ttk.LabelFrame(frame, text="手动映射改名", padding=6)
    manual_frame.grid(row=2, column=0, columnspan=8, sticky="nsew", padx=4, pady=6)
    old_field_var = tk.StringVar(value=headers[0] if headers else "")
    new_field_var = tk.StringVar(value="")
    ttk.Label(manual_frame, text="原字段名：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
    ttk.Combobox(manual_frame, textvariable=old_field_var, values=headers, width=28, state="normal").grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
    ttk.Label(manual_frame, text="新字段名：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
    ttk.Entry(manual_frame, textvariable=new_field_var, width=30).grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)

    map_wrap = ttk.Frame(manual_frame)
    map_wrap.grid(row=1, column=0, columnspan=6, sticky="nsew", padx=4, pady=4)
    mapping_tree = ttk.Treeview(map_wrap, columns=("old", "new"), show="headings", height=8)
    mapping_tree.heading("old", text="原字段名")
    mapping_tree.heading("new", text="新字段名")
    mapping_tree.column("old", width=260, anchor=tk.W)
    mapping_tree.column("new", width=260, anchor=tk.W)
    map_y = ttk.Scrollbar(map_wrap, orient=tk.VERTICAL, command=mapping_tree.yview)
    mapping_tree.configure(yscrollcommand=map_y.set)
    mapping_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    map_y.pack(side=tk.RIGHT, fill=tk.Y)
    manual_frame.rowconfigure(1, weight=1)
    manual_frame.columnconfigure(5, weight=1)

    return {
        "frame": manual_frame,
        "old_field_var": old_field_var,
        "new_field_var": new_field_var,
        "mapping_tree": mapping_tree,
    }


def refresh_rename_mapping_tree(manual_section, config):
    mapping_tree = manual_section["mapping_tree"]
    mapping_tree.delete(*mapping_tree.get_children())
    for item in config.get("mappings", []):
        mapping_tree.insert("", tk.END, values=(item.get("old", ""), item.get("new", "")))


def save_rename_mapping_tree_to_config(manual_section, config):
    mapping_tree = manual_section["mapping_tree"]
    items = []
    for iid in mapping_tree.get_children():
        old, new = mapping_tree.item(iid, "values")[:2]
        if str(old).strip():
            items.append({"old": str(old), "new": str(new)})
    config["mappings"] = items


def add_rename_mapping(manual_section, config):
    old = manual_section["old_field_var"].get().strip()
    new = manual_section["new_field_var"].get().strip()
    if not old:
        messagebox.showwarning("提示", "请先填写原字段名。")
        return
    manual_section["mapping_tree"].insert("", tk.END, values=(old, new))
    save_rename_mapping_tree_to_config(manual_section, config)


def delete_rename_mapping(manual_section, config):
    mapping_tree = manual_section["mapping_tree"]
    for iid in mapping_tree.selection():
        mapping_tree.delete(iid)
    save_rename_mapping_tree_to_config(manual_section, config)


def clear_rename_mapping(manual_section, config):
    mapping_tree = manual_section["mapping_tree"]
    mapping_tree.delete(*mapping_tree.get_children())
    save_rename_mapping_tree_to_config(manual_section, config)


def load_all_headers_to_rename_mapping(manual_section, config, headers):
    mapping_tree = manual_section["mapping_tree"]
    mapping_tree.delete(*mapping_tree.get_children())
    for header in headers:
        mapping_tree.insert("", tk.END, values=(header, header))
    save_rename_mapping_tree_to_config(manual_section, config)


def load_selected_header_to_rename_new_name(manual_section):
    old = manual_section["old_field_var"].get().strip()
    if old:
        manual_section["new_field_var"].set(old)


def edit_rename_mapping_cell(manual_section, config, event):
    mapping_tree = manual_section["mapping_tree"]
    region = mapping_tree.identify("region", event.x, event.y)
    if region != "cell":
        return
    row_id = mapping_tree.identify_row(event.y)
    col_id = mapping_tree.identify_column(event.x)
    if not row_id or not col_id:
        return
    col_index = int(col_id.replace("#", "")) - 1
    bbox = mapping_tree.bbox(row_id, col_id)
    if not bbox:
        return
    x, y, width, height = bbox
    values = list(mapping_tree.item(row_id, "values"))
    entry = ttk.Entry(mapping_tree)
    entry.place(x=x, y=y, width=width, height=height)
    entry.insert(0, values[col_index] if col_index < len(values) else "")
    entry.select_range(0, tk.END)
    entry.focus()

    def close(save=True):
        if save:
            while len(values) < 2:
                values.append("")
            values[col_index] = entry.get()
            mapping_tree.item(row_id, values=values)
            save_rename_mapping_tree_to_config(manual_section, config)
        entry.destroy()

    entry.bind("<Return>", lambda _event: close(True))
    entry.bind("<Escape>", lambda _event: close(False))
    entry.bind("<FocusOut>", lambda _event: close(True))


def build_rename_columns_manual_action_buttons(manual_section, config, headers):
    manual_frame = manual_section["frame"]
    btns = ttk.Frame(manual_frame)
    btns.grid(row=0, column=4, rowspan=2, sticky="ns", padx=4, pady=4)
    for text, command in [
        ("添加映射", lambda: add_rename_mapping(manual_section, config)),
        ("删除选中", lambda: delete_rename_mapping(manual_section, config)),
        ("清空映射", lambda: clear_rename_mapping(manual_section, config)),
        ("载入全部字段", lambda: load_all_headers_to_rename_mapping(manual_section, config, headers)),
        ("新名=原名", lambda: load_selected_header_to_rename_new_name(manual_section)),
        ("保存映射", lambda: save_rename_mapping_tree_to_config(manual_section, config)),
    ]:
        ttk.Button(btns, text=text, command=command).pack(fill=tk.X, pady=2)
    manual_section["mapping_tree"].bind("<Double-1>", lambda event: edit_rename_mapping_cell(manual_section, config, event))
    refresh_rename_mapping_tree(manual_section, config)


def build_rename_columns_rule_section(window, frame, config):
    rule_frame = ttk.LabelFrame(frame, text="批量规则", padding=6)
    rule_frame.grid(row=3, column=0, columnspan=8, sticky="ew", padx=4, pady=6)
    prefix_var = window.add_labeled_entry(rule_frame, "前缀：", config.get("prefix", ""), 0, 0, 18)
    suffix_var = window.add_labeled_entry(rule_frame, "后缀：", config.get("suffix", ""), 0, 2, 18)
    match_var = window.add_labeled_entry(rule_frame, "匹配值：", config.get("replace_match", ""), 1, 0, 18)
    repl_var = window.add_labeled_entry(rule_frame, "替换值：", config.get("replace_value", ""), 1, 2, 18)
    scope_var = window.add_labeled_combo(rule_frame, "作用范围：", config.get("scope", "全部字段"), SCOPE_VALUES, 2, 0, 16)
    for var, key in [(prefix_var, "prefix"), (suffix_var, "suffix"), (match_var, "replace_match"), (repl_var, "replace_value"), (scope_var, "scope")]:
        window.sync_var_to_config(var, config, key)
    return {
        "frame": rule_frame,
        "prefix_var": prefix_var,
        "suffix_var": suffix_var,
        "match_var": match_var,
        "repl_var": repl_var,
        "scope_var": scope_var,
    }


def sync_rename_scope_fields(field_section, config):
    listbox = field_section["listbox"]
    config["scope_fields"] = [listbox.get(index) for index in listbox.curselection()]


def build_rename_columns_scope_section(frame, config, headers):
    field_frame = ttk.LabelFrame(frame, text="选中字段范围（作用范围为“选中字段”时使用）", padding=6)
    field_frame.grid(row=4, column=0, columnspan=8, sticky="nsew", padx=4, pady=6)
    listbox = tk.Listbox(field_frame, selectmode=tk.MULTIPLE, height=8, exportselection=False)
    yscroll = ttk.Scrollbar(field_frame, orient=tk.VERTICAL, command=listbox.yview)
    listbox.configure(yscrollcommand=yscroll.set)
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    yscroll.pack(side=tk.RIGHT, fill=tk.Y)
    selected = set(config.get("scope_fields", []))
    for index, header in enumerate(headers):
        listbox.insert(tk.END, header)
        if header in selected:
            listbox.selection_set(index)
    section = {
        "frame": field_frame,
        "listbox": listbox,
    }
    listbox.bind("<<ListboxSelect>>", lambda *_: sync_rename_scope_fields(section, config))
    return section


def build_rename_columns_scope_action_buttons(field_section, config):
    listbox = field_section["listbox"]
    scope_btns = ttk.Frame(field_section["frame"])
    scope_btns.pack(side=tk.LEFT, fill=tk.Y, padx=6)
    ttk.Button(scope_btns, text="保存勾选", command=lambda: sync_rename_scope_fields(field_section, config)).pack(fill=tk.X, pady=2)
    ttk.Button(scope_btns, text="全选", command=lambda: (listbox.selection_set(0, tk.END), sync_rename_scope_fields(field_section, config))).pack(fill=tk.X, pady=2)
    ttk.Button(scope_btns, text="全不选", command=lambda: (listbox.selection_clear(0, tk.END), sync_rename_scope_fields(field_section, config))).pack(fill=tk.X, pady=2)


def build_rename_columns_footer(frame):
    ttk.Label(
        frame,
        text="说明：手动映射模式只修改映射中列出的字段；批量模式可对全部字段或选中字段添加前缀/后缀/替换字符。执行前请先预览计划，确认字段名无误。",
        foreground="gray",
        wraplength=1050,
    ).grid(row=5, column=0, columnspan=8, sticky=tk.W, padx=4, pady=(6, 2))


def build_rename_columns_config(window, config, headers):
    frame = ttk.LabelFrame(window.config_frame, text="批量更改列名节点", padding=8)
    frame.pack(fill=tk.BOTH, expand=True, pady=8)
    build_rename_columns_general_section(window, frame, config)
    manual_section = build_rename_columns_manual_section(frame, config, headers)
    build_rename_columns_manual_action_buttons(manual_section, config, headers)
    build_rename_columns_rule_section(window, frame, config)
    scope_section = build_rename_columns_scope_section(frame, config, headers)
    build_rename_columns_scope_action_buttons(scope_section, config)
    build_rename_columns_footer(frame)
