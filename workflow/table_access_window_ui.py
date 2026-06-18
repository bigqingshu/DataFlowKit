# -*- coding: utf-8 -*-
"""Small UI/data helpers for the table-access editor window."""

import tkinter as tk
from tkinter import ttk

from workflow.table_access_window_callbacks import (
    create_table_access_field_action_callbacks,
    create_table_access_selection_callbacks,
    create_table_access_table_action_callbacks,
    create_table_access_window_callbacks,
)
from workflow.table_access_window_logic import (
    add_table_access_entry,
    apply_auto_field_mapping_by_name,
    apply_auto_field_mapping_by_order,
    build_auto_field_mapping_by_name,
    build_auto_field_mapping_by_order,
    build_table_access_impact_preview,
    build_table_access_permission_check,
    clear_field_mapping,
    delete_field_mapping_entry,
    delete_table_access_entry,
    ensure_field_mapping_dict,
    ensure_table_entries,
    field_mapping_item,
    field_mapping_mode_display,
    field_mapping_mode_value,
    load_field_form,
    make_table_access_field_key,
    rebuild_table_access,
    render_field_mapping_tree,
    render_table_access_tree,
    reset_field_form,
    save_table_access_entry,
    selected_field_key,
    table_access_field_mapping_mode_choices,
    table_access_field_tree_columns,
    table_access_node_tree_columns,
    table_access_preset_choices,
    table_access_preset_config,
    table_access_role_choices,
    table_access_source_type_choices,
    table_access_table_tree_columns,
    upsert_field_mapping_entry,
)


def build_table_access_window_shell(window):
    win = tk.Toplevel(window.window)
    win.title("字段权限层")
    win.geometry("1180x720")
    win.minsize(900, 560)
    win.transient(window.window)

    main = ttk.Frame(win, padding=8)
    main.pack(fill=tk.BOTH, expand=True)

    panes = ttk.Panedwindow(main, orient=tk.HORIZONTAL)
    panes.pack(fill=tk.BOTH, expand=True)

    left = ttk.LabelFrame(panes, text="节点层", padding=6)
    detail = ttk.Frame(panes)
    panes.add(left, weight=1)
    panes.add(detail, weight=3)

    detail_tabs = ttk.Notebook(detail)
    detail_tabs.pack(fill=tk.BOTH, expand=True)
    middle = ttk.Frame(detail_tabs, padding=6)
    right = ttk.Frame(detail_tabs, padding=6)
    detail_tabs.add(middle, text="表权限层")
    detail_tabs.add(right, text="字段权限层")

    return {
        "win": win,
        "left": left,
        "middle": middle,
        "right": right,
    }


def build_table_access_list_section(window, parent):
    node_tree = ttk.Treeview(
        parent,
        columns=("index", "type", "name", "status"),
        show="headings",
        height=22,
    )
    for col, text, width in table_access_node_tree_columns():
        node_tree.heading(col, text=text)
        node_tree.column(col, width=width, anchor=tk.W)
    node_y = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=node_tree.yview)
    node_tree.configure(yscrollcommand=node_y.set)
    node_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    node_y.pack(side=tk.RIGHT, fill=tk.Y)
    return {"node_tree": node_tree}


def build_table_access_table_form_section(window, parent):
    table_tree_frame = ttk.Frame(parent)
    table_tree_frame.pack(fill=tk.BOTH, expand=True)
    table_tree = ttk.Treeview(
        table_tree_frame,
        columns=("role", "table", "operation", "current", "permissions", "mode", "status"),
        show="headings",
        height=12,
    )
    for col, text, width in table_access_table_tree_columns():
        table_tree.heading(col, text=text)
        table_tree.column(col, width=width, anchor=tk.W, stretch=False)
    table_y = ttk.Scrollbar(table_tree_frame, orient=tk.VERTICAL, command=table_tree.yview)
    table_x = ttk.Scrollbar(table_tree_frame, orient=tk.HORIZONTAL, command=table_tree.xview)
    table_tree.configure(yscrollcommand=table_y.set, xscrollcommand=table_x.set)
    table_tree.grid(row=0, column=0, sticky="nsew")
    table_y.grid(row=0, column=1, sticky="ns")
    table_x.grid(row=1, column=0, sticky="ew")
    table_tree_frame.rowconfigure(0, weight=1)
    table_tree_frame.columnconfigure(0, weight=1)

    table_form = ttk.LabelFrame(parent, text="表角色设置", padding=6)
    table_form.pack(fill=tk.X, pady=(6, 0))
    role_var = tk.StringVar()
    source_type_var = tk.StringVar(value="SQLite表")
    table_var = tk.StringVar()
    write_mode_var = tk.StringVar()
    preset_var = tk.StringVar(value="自定义")
    is_current_var = tk.BooleanVar(value=False)
    log_only_var = tk.BooleanVar(value=False)
    permission_vars = {key: tk.BooleanVar(value=False) for key, _ in window.table_access_permission_items()}

    ttk.Label(table_form, text="角色").grid(row=0, column=0, sticky=tk.W, padx=3, pady=3)
    ttk.Combobox(table_form, textvariable=role_var, values=table_access_role_choices(), width=12).grid(row=0, column=1, sticky=tk.W, padx=3, pady=3)
    ttk.Label(table_form, text="来源").grid(row=0, column=2, sticky=tk.W, padx=3, pady=3)
    ttk.Combobox(table_form, textvariable=source_type_var, values=table_access_source_type_choices(), width=12, state="readonly").grid(row=0, column=3, sticky=tk.W, padx=3, pady=3)
    ttk.Label(table_form, text="实际表").grid(row=1, column=0, sticky=tk.W, padx=3, pady=3)
    table_combo = ttk.Combobox(table_form, textvariable=table_var, values=window.table_access_table_choices(), width=25)
    table_combo.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=3, pady=3)
    ttk.Label(table_form, text="写入模式").grid(row=1, column=3, sticky=tk.W, padx=3, pady=3)
    ttk.Combobox(
        table_form,
        textvariable=write_mode_var,
        values=window.STANDARD_WRITE_MODE_CHOICES,
        width=19,
    ).grid(row=1, column=4, sticky=tk.W, padx=3, pady=3)
    ttk.Label(table_form, text="预设").grid(row=2, column=0, sticky=tk.W, padx=3, pady=3)
    preset_combo = ttk.Combobox(
        table_form,
        textvariable=preset_var,
        values=table_access_preset_choices(),
        width=18,
        state="readonly",
    )
    preset_combo.grid(row=2, column=1, sticky=tk.W, padx=3, pady=3)
    ttk.Checkbutton(table_form, text="当前表", variable=is_current_var).grid(row=2, column=2, sticky=tk.W, padx=3, pady=3)
    ttk.Checkbutton(table_form, text="只记录", variable=log_only_var).grid(row=2, column=3, sticky=tk.W, padx=3, pady=3)
    ttk.Label(table_form, text="字段权限范围").grid(row=4, column=0, sticky=tk.W, padx=3, pady=3)
    field_mapping_mode_var = tk.StringVar(value="按字段名")
    ttk.Combobox(
        table_form,
        textvariable=field_mapping_mode_var,
        values=table_access_field_mapping_mode_choices(),
        width=12,
        state="readonly",
    ).grid(row=4, column=1, sticky=tk.W, padx=3, pady=3)

    perm_frame = ttk.Frame(table_form)
    perm_frame.grid(row=3, column=0, columnspan=5, sticky=tk.W, pady=(4, 0))
    for idx, (key, label) in enumerate(window.table_access_permission_items()):
        ttk.Checkbutton(perm_frame, text=label, variable=permission_vars[key]).grid(row=idx // 5, column=idx % 5, sticky=tk.W, padx=4, pady=2)

    return {
        "table_tree": table_tree,
        "table_form": table_form,
        "role_var": role_var,
        "source_type_var": source_type_var,
        "table_var": table_var,
        "write_mode_var": write_mode_var,
        "preset_var": preset_var,
        "preset_combo": preset_combo,
        "is_current_var": is_current_var,
        "log_only_var": log_only_var,
        "permission_vars": permission_vars,
        "field_mapping_mode_var": field_mapping_mode_var,
        "table_combo": table_combo,
    }


def build_table_access_field_form_section(window, parent):
    field_tree_frame = ttk.Frame(parent)
    field_tree_frame.pack(fill=tk.BOTH, expand=True)
    field_tree = ttk.Treeview(
        field_tree_frame,
        columns=("source_index", "source", "target_index", "target", "read", "write", "create", "protect", "status"),
        show="headings",
        height=14,
    )
    for col, text, width in table_access_field_tree_columns():
        field_tree.heading(col, text=text)
        field_tree.column(col, width=width, anchor=tk.W, stretch=False)
    field_y = ttk.Scrollbar(field_tree_frame, orient=tk.VERTICAL, command=field_tree.yview)
    field_x = ttk.Scrollbar(field_tree_frame, orient=tk.HORIZONTAL, command=field_tree.xview)
    field_tree.configure(yscrollcommand=field_y.set, xscrollcommand=field_x.set)
    field_tree.grid(row=0, column=0, sticky="nsew")
    field_y.grid(row=0, column=1, sticky="ns")
    field_x.grid(row=1, column=0, sticky="ew")
    field_tree_frame.rowconfigure(0, weight=1)
    field_tree_frame.columnconfigure(0, weight=1)

    field_form = ttk.LabelFrame(parent, text="字段权限设置", padding=6)
    field_form.pack(fill=tk.X, pady=(6, 0))
    source_field_var = tk.StringVar()
    target_field_var = tk.StringVar()
    source_index_var = tk.StringVar()
    target_index_var = tk.StringVar()
    field_permission_vars = {key: tk.BooleanVar(value=False) for key, _ in window.field_permission_items()}

    ttk.Label(field_form, text="来源字段").grid(row=0, column=0, sticky=tk.W, padx=3, pady=3)
    source_field_combo = ttk.Combobox(field_form, textvariable=source_field_var, width=22)
    source_field_combo.grid(row=0, column=1, sticky=tk.W, padx=3, pady=3)
    ttk.Label(field_form, text="源序号").grid(row=0, column=2, sticky=tk.W, padx=3, pady=3)
    ttk.Entry(field_form, textvariable=source_index_var, width=6).grid(row=0, column=3, sticky=tk.W, padx=3, pady=3)
    ttk.Label(field_form, text="目标字段").grid(row=1, column=0, sticky=tk.W, padx=3, pady=3)
    target_field_combo = ttk.Combobox(field_form, textvariable=target_field_var, width=22)
    target_field_combo.grid(row=1, column=1, sticky=tk.W, padx=3, pady=3)
    ttk.Label(field_form, text="目序号").grid(row=1, column=2, sticky=tk.W, padx=3, pady=3)
    ttk.Entry(field_form, textvariable=target_index_var, width=6).grid(row=1, column=3, sticky=tk.W, padx=3, pady=3)
    fp_frame = ttk.Frame(field_form)
    fp_frame.grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(4, 0))
    for idx, (key, label) in enumerate(window.field_permission_items()):
        ttk.Checkbutton(fp_frame, text=label, variable=field_permission_vars[key]).grid(row=0, column=idx, sticky=tk.W, padx=4, pady=2)

    return {
        "field_tree": field_tree,
        "field_form": field_form,
        "source_field_var": source_field_var,
        "target_field_var": target_field_var,
        "source_index_var": source_index_var,
        "target_index_var": target_index_var,
        "field_permission_vars": field_permission_vars,
        "source_field_combo": source_field_combo,
        "target_field_combo": target_field_combo,
    }


def build_table_access_table_action_buttons(window, table_form, commands):
    table_btns = ttk.Frame(table_form)
    table_btns.grid(row=5, column=0, columnspan=5, sticky=tk.W, pady=(6, 0))
    buttons = {
        "add_table_entry": ttk.Button(table_btns, text="新增表角色", command=commands["add_table_entry"]),
        "save_table_entry": ttk.Button(table_btns, text="保存表设置", command=commands["save_table_entry"]),
        "delete_table_entry": ttk.Button(table_btns, text="删除表角色", command=commands["delete_table_entry"]),
        "rebuild_default_access": ttk.Button(table_btns, text="重建默认", command=commands["rebuild_default_access"]),
        "check_all_permissions": ttk.Button(table_btns, text="检查权限", command=commands["check_all_permissions"]),
        "preview_impact": ttk.Button(table_btns, text="预览影响", command=commands["preview_impact"]),
    }
    for button in buttons.values():
        button.pack(side=tk.LEFT, padx=3)
    return buttons


def build_table_access_field_action_buttons(window, field_form, commands):
    field_btns = ttk.Frame(field_form)
    field_btns.grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(6, 0))
    buttons = {
        "add_field_entry": ttk.Button(field_btns, text="新增字段", command=commands["add_field_entry"]),
        "save_field_entry": ttk.Button(field_btns, text="保存字段", command=commands["save_field_entry"]),
        "delete_field_entry": ttk.Button(field_btns, text="删除字段", command=commands["delete_field_entry"]),
        "auto_match_fields": ttk.Button(field_btns, text="按字段名生成权限", command=commands["auto_match_fields"]),
        "auto_match_fields_by_order": ttk.Button(field_btns, text="按列顺序生成权限", command=commands["auto_match_fields_by_order"]),
        "clear_fields": ttk.Button(field_btns, text="清空字段", command=commands["clear_fields"]),
    }
    for button in buttons.values():
        button.pack(side=tk.LEFT, padx=3)
    return buttons


def build_table_access_bottom_buttons(window, win, commands):
    bottom = ttk.Frame(win, padding=(8, 0, 8, 8))
    bottom.pack(fill=tk.X)
    buttons = {
        "refresh": ttk.Button(bottom, text="刷新节点列表", command=commands["refresh"]),
        "precheck": ttk.Button(bottom, text="权限预检", command=commands["precheck"]),
        "audit": ttk.Button(bottom, text="审计日志", command=commands["audit"]),
        "close": ttk.Button(bottom, text="关闭", command=commands["close"]),
    }
    buttons["refresh"].pack(side=tk.LEFT, padx=4)
    buttons["precheck"].pack(side=tk.LEFT, padx=4)
    buttons["audit"].pack(side=tk.LEFT, padx=4)
    buttons["close"].pack(side=tk.RIGHT, padx=4)
    return buttons


def current_table_access_window_node(window, state):
    idx = state.get("node_index")
    if idx is None or idx < 0 or idx >= len(window.nodes):
        return None
    return window.nodes[idx]


def refresh_table_access_node_tree(window, node_tree, state):
    state["refreshing_node_tree"] = True
    try:
        node_tree.delete(*node_tree.get_children())
        for idx, node in enumerate(window.nodes):
            mark = "√" if node.get("enabled", True) else "×"
            node_tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(idx + 1, f"{mark} {node.get('type', '')}", node.get("name", ""), window.table_access_node_status(node)),
            )
        selected = state.get("node_index")
        if selected is not None and 0 <= selected < len(window.nodes):
            node_tree.selection_set(str(selected))
            node_tree.focus(str(selected))
    finally:
        state["refreshing_node_tree"] = False


def load_table_access_table_form(window, table_section, entry, table_choices):
    entry = entry or {}
    table_section["role_var"].set(entry.get("role", "target"))
    table_section["source_type_var"].set(entry.get("source_type", "SQLite表"))
    table_section["table_var"].set(entry.get("table", ""))
    table_section["write_mode_var"].set(window.normalize_table_access_write_mode(entry.get("write_mode", "")))
    table_section["field_mapping_mode_var"].set(field_mapping_mode_display(entry))
    table_section["is_current_var"].set(bool(entry.get("is_current_table")))
    table_section["log_only_var"].set(bool(entry.get("log_only")))
    perms = entry.get("permissions") or {}
    for key, var in table_section["permission_vars"].items():
        var.set(bool(perms.get(key)))
    table_section["preset_var"].set("自定义")
    table_section["table_combo"].configure(values=table_choices)


def refresh_table_access_field_choices(window, field_section, choices):
    field_section["source_field_combo"].configure(values=choices)
    field_section["target_field_combo"].configure(values=choices)


def refresh_table_access_field_tree(window, state, field_tree, entry, field_section, choices):
    state["field_keys"] = render_field_mapping_tree(
        field_tree,
        entry,
        window.field_bool_text,
        window.field_permission_status,
    )
    refresh_table_access_field_choices(window, field_section, choices)


def current_table_access_window_access(window, state):
    node = current_table_access_window_node(window, state)
    return window.get_node_table_access(node) if node is not None else {"tables": []}


def current_table_access_window_table_entry(window, state):
    access = current_table_access_window_access(window, state)
    idx = state.get("table_index")
    tables = access.get("tables", [])
    if idx is None or idx < 0 or idx >= len(tables):
        return None
    return tables[idx]


def load_table_access_window_table_form(window, state, table_section, entry):
    load_table_access_table_form(
        window,
        table_section,
        entry,
        window.table_access_table_choices(current_table_access_window_node(window, state)),
    )


def collect_table_access_window_table_form(window, table_section):
    permission_vars = table_section["permission_vars"]
    return {
        "role": table_section["role_var"].get(),
        "source_type": table_section["source_type_var"].get(),
        "table": table_section["table_var"].get(),
        "is_current_table": table_section["is_current_var"].get(),
        "log_only": table_section["log_only_var"].get(),
        "write_mode": window.normalize_table_access_write_mode(table_section["write_mode_var"].get()),
        "field_mapping_mode": field_mapping_mode_value(table_section["field_mapping_mode_var"].get()),
        "permissions": {key: bool(var.get()) for key, var in permission_vars.items()},
    }


def refresh_table_access_window_field_tree(window, state, field_section, field_tree):
    entry = current_table_access_window_table_entry(window, state)
    refresh_table_access_field_tree(
        window,
        state,
        field_tree,
        entry,
        field_section,
        window.get_table_access_field_choices(state.get("node_index") or 0, entry or {}),
    )


def refresh_table_access_window_table_tree(
    window,
    state,
    table_section,
    field_section,
    node_tree,
    table_tree,
    field_tree,
    select_index=None,
):
    access = current_table_access_window_access(window, state)
    tables = access.get("tables", [])
    if tables:
        if select_index is None:
            select_index = state.get("table_index")
        select_index = render_table_access_tree(
            table_tree,
            tables,
            window.table_access_entry_table_label,
            window.table_access_operation_summary,
            window.table_permission_summary,
            window.write_mode_display_text,
            window.table_access_entry_status,
            select_index=select_index,
        )
        state["table_index"] = select_index
        load_table_access_window_table_form(window, state, table_section, tables[select_index])
    else:
        render_table_access_tree(
            table_tree,
            tables,
            window.table_access_entry_table_label,
            window.table_access_operation_summary,
            window.table_permission_summary,
            window.write_mode_display_text,
            window.table_access_entry_status,
        )
        state["table_index"] = None
        load_table_access_window_table_form(window, state, table_section, {})
    refresh_table_access_window_field_tree(window, state, field_section, field_tree)
    refresh_table_access_node_tree(window, node_tree, state)


def on_table_access_window_node_selected(
    window,
    state,
    table_section,
    field_section,
    node_tree,
    table_tree,
    field_tree,
    status_var,
    event=None,
    force=False,
):
    if state.get("refreshing_node_tree"):
        return
    sel = node_tree.selection()
    if not sel:
        return
    selected_index = int(sel[0])
    if not force and selected_index == state.get("node_index"):
        return
    state["node_index"] = selected_index
    state["table_index"] = None
    refresh_table_access_window_table_tree(
        window,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
    )
    node = current_table_access_window_node(window, state)
    if node:
        status_var.set(f"当前节点：{state['node_index'] + 1}.{node.get('type')} / {node.get('name', '')}")


def on_table_access_window_table_selected(
    window,
    state,
    table_section,
    field_section,
    table_tree,
    field_tree,
    event=None,
):
    sel = table_tree.selection()
    if not sel:
        return
    state["table_index"] = int(sel[0])
    entry = current_table_access_window_table_entry(window, state)
    load_table_access_window_table_form(window, state, table_section, entry)
    refresh_table_access_window_field_tree(window, state, field_section, field_tree)


def on_table_access_window_field_selected(window, state, field_section, field_tree, event=None):
    sel = field_tree.selection()
    if not sel:
        return
    row_idx = int(sel[0])
    entry = current_table_access_window_table_entry(window, state)
    if not entry or row_idx >= len(state["field_keys"]):
        return
    key = state["field_keys"][row_idx]
    item = field_mapping_item(entry, key)
    if item is None:
        return
    load_field_form(
        item,
        field_section["source_field_var"],
        field_section["target_field_var"],
        field_section["source_index_var"],
        field_section["target_index_var"],
        field_section["field_permission_vars"],
    )


def save_table_access_window_table_entry(
    window,
    state,
    table_section,
    field_section,
    node_tree,
    table_tree,
    field_tree,
    status_var,
):
    from workflow import table_access_window_actions

    return table_access_window_actions.save_table_access_window_table_entry(
        window,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    )


def add_table_access_window_table_entry(
    window,
    state,
    table_section,
    field_section,
    node_tree,
    table_tree,
    field_tree,
):
    from workflow import table_access_window_actions

    return table_access_window_actions.add_table_access_window_table_entry(
        window,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
    )


def delete_table_access_window_table_entry(
    window,
    state,
    table_section,
    field_section,
    node_tree,
    table_tree,
    field_tree,
    status_var,
):
    from workflow import table_access_window_actions

    return table_access_window_actions.delete_table_access_window_table_entry(
        window,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    )


def rebuild_table_access_window_default_access(
    window,
    win,
    state,
    table_section,
    field_section,
    node_tree,
    table_tree,
    field_tree,
    status_var,
):
    from workflow import table_access_window_actions

    return table_access_window_actions.rebuild_table_access_window_default_access(
        window,
        win,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    )


def check_table_access_window_permissions(window, win, status_var):
    from workflow import table_access_window_actions

    return table_access_window_actions.check_table_access_window_permissions(window, win, status_var)


def preview_table_access_window_impact(window, win, state):
    from workflow import table_access_window_actions

    return table_access_window_actions.preview_table_access_window_impact(window, win, state)


def apply_table_access_window_table_preset(window, table_section, event=None):
    from workflow import table_access_window_actions

    return table_access_window_actions.apply_table_access_window_table_preset(window, table_section, event=event)


def save_table_access_window_field_entry(window, state, table_section, field_section, field_tree, status_var):
    from workflow import table_access_window_actions

    return table_access_window_actions.save_table_access_window_field_entry(
        window, state, table_section, field_section, field_tree, status_var
    )


def add_table_access_window_field_entry(window, table_section, field_section, field_tree):
    from workflow import table_access_window_actions

    return table_access_window_actions.add_table_access_window_field_entry(
        window, table_section, field_section, field_tree
    )


def delete_table_access_window_field_entry(window, state, field_section, field_tree, status_var):
    from workflow import table_access_window_actions

    return table_access_window_actions.delete_table_access_window_field_entry(
        window, state, field_section, field_tree, status_var
    )


def auto_match_table_access_window_fields(window, state, field_section, field_tree, status_var):
    from workflow import table_access_window_actions

    return table_access_window_actions.auto_match_table_access_window_fields(
        window, state, field_section, field_tree, status_var
    )


def auto_match_table_access_window_fields_by_order(window, state, table_section, field_section, field_tree, status_var):
    from workflow import table_access_window_actions

    return table_access_window_actions.auto_match_table_access_window_fields_by_order(
        window, state, table_section, field_section, field_tree, status_var
    )


def clear_table_access_window_fields(window, state, field_section, field_tree, status_var):
    from workflow import table_access_window_actions

    return table_access_window_actions.clear_table_access_window_fields(
        window, state, field_section, field_tree, status_var
    )


def open_table_access_window(window, initial_index=None):
    window.ensure_node_tree_identity(window.nodes)
    if initial_index is None:
        initial_index = window.get_selected_node_index()
    if initial_index is None and window.nodes:
        initial_index = 0

    state = {"node_index": initial_index, "table_index": None, "field_keys": [], "refreshing_node_tree": False}

    shell = window.build_table_access_window_shell()
    win = shell["win"]
    left = shell["left"]
    middle = shell["middle"]
    right = shell["right"]

    left_section = window.build_table_access_list_section(left)
    node_tree = left_section["node_tree"]

    table_section = window.build_table_access_table_form_section(middle)
    table_tree = table_section["table_tree"]
    table_form = table_section["table_form"]
    preset_combo = table_section["preset_combo"]

    field_section = window.build_table_access_field_form_section(right)
    field_tree = field_section["field_tree"]
    field_form = field_section["field_form"]

    status_var = tk.StringVar(value="选择节点后可编辑表权限与字段映射。")
    ttk.Label(win, textvariable=status_var, foreground="gray").pack(fill=tk.X, padx=8, pady=(0, 6))

    callbacks = window.create_table_access_window_callbacks(
        win,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    )

    preset_combo.bind("<<ComboboxSelected>>", callbacks["apply_table_preset"])
    node_tree.bind("<<TreeviewSelect>>", callbacks["on_node_selected"])
    table_tree.bind("<<TreeviewSelect>>", callbacks["on_table_selected"])
    field_tree.bind("<<TreeviewSelect>>", callbacks["on_field_selected"])

    window.build_table_access_table_action_buttons(
        table_form,
        {
            "add_table_entry": callbacks["add_table_entry"],
            "save_table_entry": callbacks["save_table_entry"],
            "delete_table_entry": callbacks["delete_table_entry"],
            "rebuild_default_access": callbacks["rebuild_default_access"],
            "check_all_permissions": callbacks["check_all_permissions"],
            "preview_impact": callbacks["preview_impact"],
        },
    )
    window.build_table_access_field_action_buttons(
        field_form,
        {
            "add_field_entry": callbacks["add_field_entry"],
            "save_field_entry": callbacks["save_field_entry"],
            "delete_field_entry": callbacks["delete_field_entry"],
            "auto_match_fields": callbacks["auto_match_fields"],
            "auto_match_fields_by_order": callbacks["auto_match_fields_by_order"],
            "clear_fields": callbacks["clear_fields"],
        },
    )
    window.build_table_access_bottom_buttons(
        win,
        {
            "refresh": lambda: (callbacks["refresh_node_tree"](), callbacks["refresh_table_tree"](state.get("table_index"))),
            "precheck": window.open_table_access_precheck_window,
            "audit": window.open_table_access_audit_window,
            "close": win.destroy,
        },
    )

    callbacks["refresh_node_tree"]()
    if window.nodes:
        initial_index = max(0, min(int(initial_index or 0), len(window.nodes) - 1))
        node_tree.selection_set(str(initial_index))
        node_tree.focus(str(initial_index))
        callbacks["on_node_selected"](force=True)
    else:
        status_var.set("当前没有节点，请先添加工作流节点。")
