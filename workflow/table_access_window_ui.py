# -*- coding: utf-8 -*-
"""Small UI/data helpers for the table-access editor window."""

import tkinter as tk
from tkinter import ttk, messagebox

from workflow.table_access_precheck import table_access_field_items


def table_access_node_tree_columns():
    return [
        ("index", "#", 44),
        ("type", "节点类型", 130),
        ("name", "节点名称", 145),
        ("status", "状态", 80),
    ]


def table_access_table_tree_columns():
    return [
        ("role", "表角色", 80),
        ("table", "实际表", 150),
        ("operation", "操作", 160),
        ("current", "当前表", 58),
        ("permissions", "权限摘要", 145),
        ("mode", "写入模式", 120),
        ("status", "状态", 75),
    ]


def table_access_field_tree_columns():
    return [
        ("source_index", "源序", 48),
        ("source", "来源字段", 110),
        ("target_index", "目序", 48),
        ("target", "目标字段", 110),
        ("read", "读", 42),
        ("write", "写", 42),
        ("create", "建", 42),
        ("protect", "保护", 52),
        ("status", "状态", 70),
    ]


def table_access_role_choices():
    return ["current", "source", "target", "lookup", "transit", "output", "log"]


def table_access_source_type_choices():
    return ["当前工作流表", "SQLite表", "中转副表"]


def table_access_preset_choices():
    return ["自定义", "禁止访问", "只读", "默认读写只记录", "追加写入", "更新写入", "追加或更新", "覆盖/清空", "新建表", "危险全开"]


def table_access_field_mapping_mode_choices():
    return ["按字段名", "按列顺序", "手动"]


def field_mapping_mode_display(entry):
    mode = str((entry or {}).get("field_mapping_mode", "by_name") or "by_name").strip()
    return {
        "by_order": "按列顺序",
        "order": "按列顺序",
        "按列顺序": "按列顺序",
        "manual": "手动",
        "手动": "手动",
    }.get(mode, "按字段名")


def field_mapping_mode_value(display):
    return {
        "按列顺序": "by_order",
        "手动": "manual",
    }.get(str(display or "").strip(), "by_name")


def make_table_access_field_key(mapping, source_field, target_field):
    base = str(target_field or source_field or "字段").strip() or "字段"
    base = "_".join(base.split())
    key = base
    counter = 2
    while isinstance(mapping, dict) and key in mapping:
        key = f"{base}_{counter}"
        counter += 1
    return key


def render_table_access_tree(
    table_tree,
    entries,
    table_label,
    operation_summary,
    permission_summary,
    write_mode_text,
    entry_status,
    select_index=None,
):
    table_tree.delete(*table_tree.get_children())
    entries = list(entries or [])
    for idx, entry in enumerate(entries):
        table_tree.insert(
            "",
            "end",
            iid=str(idx),
            values=(
                entry.get("role", ""),
                table_label(entry),
                operation_summary(entry),
                "是" if entry.get("is_current_table") else "否",
                permission_summary(entry),
                write_mode_text(entry.get("write_mode", "")),
                entry_status(entry),
            ),
        )
    if not entries:
        return None
    if select_index is None or select_index < 0 or select_index >= len(entries):
        select_index = 0
    table_tree.selection_set(str(select_index))
    table_tree.focus(str(select_index))
    return select_index


def render_field_mapping_tree(field_tree, entry, bool_text, permission_status):
    field_tree.delete(*field_tree.get_children())
    field_keys = []
    if not entry:
        return field_keys
    for row_idx, (key, item) in enumerate(table_access_field_items(entry)):
        field_keys.append(key)
        perms = item.get("permissions") or {}
        field_tree.insert(
            "",
            "end",
            iid=str(row_idx),
            values=(
                item.get("source_index", ""),
                item.get("source_field", ""),
                item.get("target_index", ""),
                item.get("target_field", ""),
                bool_text(perms.get("read_field")),
                bool_text(perms.get("write_field")),
                bool_text(perms.get("create_field")),
                bool_text(perms.get("protect_field")),
                permission_status(item),
            ),
        )
    return field_keys


def selected_field_key(selection, field_keys):
    if not selection:
        return None
    try:
        row_idx = int(selection[0])
    except Exception:
        return None
    if 0 <= row_idx < len(field_keys or []):
        return field_keys[row_idx]
    return None


def field_mapping_item(entry, key):
    mapping = (entry or {}).get("field_mapping") or {}
    item = mapping.get(key) if isinstance(mapping, dict) else None
    return item if isinstance(item, dict) else None


def load_field_form(item, source_field_var, target_field_var, source_index_var, target_index_var, permission_vars):
    source_field_var.set(item.get("source_field", ""))
    target_field_var.set(item.get("target_field", ""))
    source_index_var.set(item.get("source_index", ""))
    target_index_var.set(item.get("target_index", ""))
    perms = item.get("permissions") or {}
    for pkey, var in permission_vars.items():
        var.set(bool(perms.get(pkey)))


def reset_field_form(source_field_var, target_field_var, source_index_var, target_index_var, permission_vars, write_enabled=False):
    source_field_var.set("")
    target_field_var.set("")
    source_index_var.set("")
    target_index_var.set("")
    permission_vars["read_field"].set(True)
    permission_vars["write_field"].set(bool(write_enabled))
    permission_vars["create_field"].set(False)
    permission_vars["protect_field"].set(False)


def ensure_field_mapping_dict(entry):
    mapping = (entry or {}).get("field_mapping")
    if not isinstance(mapping, dict):
        mapping = {}
        entry["field_mapping"] = mapping
    return mapping


def upsert_field_mapping_entry(
    entry,
    key,
    source_field,
    target_field,
    source_index,
    target_index,
    match_mode,
    permissions,
    make_key,
):
    mapping = ensure_field_mapping_dict(entry)
    if not key:
        key = make_key(mapping, source_field, target_field)
    mapping[key] = {
        "source_field": str(source_field or "").strip(),
        "target_field": str(target_field or "").strip(),
        "source_index": str(source_index or "").strip(),
        "target_index": str(target_index or "").strip(),
        "match_mode": match_mode,
        "permissions": dict(permissions or {}),
    }
    return key


def delete_field_mapping_entry(entry, key):
    mapping = (entry or {}).get("field_mapping")
    if isinstance(mapping, dict) and key in mapping:
        mapping.pop(key, None)
        return True
    return False


def clear_field_mapping(entry):
    entry["field_mapping"] = {}


def _field_mapping_permissions(entry):
    permissions = (entry or {}).get("permissions") or {}
    return {
        "read_field": True,
        "write_field": bool(permissions.get("write_table")),
        "create_field": bool(permissions.get("alter_schema")),
        "protect_field": False,
    }


def build_auto_field_mapping_by_name(source_fields, target_fields, entry, sanitize_name, make_key=None):
    source_fields = [field for field in (source_fields or []) if str(field or "").strip()]
    target_fields = [field for field in (target_fields or []) if str(field or "").strip()]
    if not target_fields:
        target_fields = list(source_fields)
    sanitize_name = sanitize_name if callable(sanitize_name) else (lambda value: str(value or "").strip())
    make_key = make_key if callable(make_key) else make_table_access_field_key

    source_by_norm = {sanitize_name(field): field for field in source_fields}
    mapping = {}
    for target in target_fields:
        norm = sanitize_name(target)
        source = target if target in source_fields else source_by_norm.get(norm, "")
        if not source:
            continue
        key = make_key(mapping, source, target)
        mapping[key] = {
            "source_field": source,
            "target_field": target,
            "permissions": _field_mapping_permissions(entry),
        }
    return mapping


def apply_auto_field_mapping_by_name(entry, source_fields, target_fields, sanitize_name, make_key=None):
    mapping = build_auto_field_mapping_by_name(source_fields, target_fields, entry, sanitize_name, make_key=make_key)
    entry["field_mapping"] = mapping
    entry["field_mapping_mode"] = "by_name"
    return len(mapping)


def build_auto_field_mapping_by_order(source_fields, target_fields, entry):
    source_fields = list(source_fields or [])
    target_fields = list(target_fields or [])
    if not target_fields:
        target_fields = list(source_fields)
    count = max(len(source_fields), len(target_fields))
    mapping = {}
    for idx in range(count):
        source = source_fields[idx] if idx < len(source_fields) else ""
        target = target_fields[idx] if idx < len(target_fields) else source
        mapping[f"col_{idx + 1}"] = {
            "source_field": source,
            "target_field": target,
            "source_index": idx + 1,
            "target_index": idx + 1,
            "match_mode": "by_order",
            "permissions": _field_mapping_permissions(entry),
        }
    return mapping


def apply_auto_field_mapping_by_order(entry, source_fields, target_fields):
    mapping = build_auto_field_mapping_by_order(source_fields, target_fields, entry)
    entry["field_mapping"] = mapping
    entry["field_mapping_mode"] = "by_order"
    return len(mapping)


def table_access_preset_config(preset, permission_keys):
    permission_keys = list(permission_keys or [])
    presets = {
        "禁止访问": {},
        "只读": {"read_table": True},
        "默认读写只记录": {"read_table": True, "write_table": True, "update_rows": True},
        "追加写入": {"read_table": True, "write_table": True, "create_table": True, "append_rows": True, "alter_schema": True},
        "更新写入": {"read_table": True, "write_table": True, "update_rows": True},
        "追加或更新": {"read_table": True, "write_table": True, "create_table": True, "append_rows": True, "update_rows": True, "alter_schema": True},
        "覆盖/清空": {"read_table": True, "write_table": True, "create_table": True, "clear_table": True, "replace_table": True},
        "新建表": {"read_table": True, "write_table": True, "create_table": True},
        "危险全开": {key: True for key in permission_keys},
    }
    selected = presets.get(preset)
    if selected is None:
        return None
    mode_by_preset = {
        "追加写入": "append",
        "更新写入": "update_by_key",
        "追加或更新": "upsert_by_key",
        "覆盖/清空": "clear_keep_schema",
        "新建表": "create_new",
        "危险全开": "replace_table",
    }
    return {
        "permissions": {key: bool(selected.get(key)) for key in permission_keys},
        "log_only": preset == "默认读写只记录",
        "write_mode": mode_by_preset.get(preset),
    }


def ensure_table_entries(access):
    tables = (access or {}).get("tables") if isinstance(access, dict) else None
    if not isinstance(tables, list):
        tables = []
        if isinstance(access, dict):
            access["tables"] = tables
    return tables


def save_table_access_entry(access, table_index, values, make_default_entry):
    tables = ensure_table_entries(access)
    idx = table_index
    if idx is None or idx < 0 or idx >= len(tables):
        entry = make_default_entry() if callable(make_default_entry) else {}
        tables.append(entry)
        idx = len(tables) - 1
    entry = tables[idx]
    values = values or {}
    table = str(values.get("table", "") or "").strip()
    is_current = bool(values.get("is_current_table") or table == "__CURRENT_TABLE__")
    entry["role"] = str(values.get("role", "") or "").strip() or "target"
    entry["source_type"] = str(values.get("source_type", "") or "").strip() or "SQLite表"
    entry["table"] = table
    entry["is_current_table"] = is_current
    entry["log_only"] = bool(values.get("log_only"))
    entry["write_mode"] = str(values.get("write_mode", "") or "").strip()
    entry["field_mapping_mode"] = str(values.get("field_mapping_mode", "") or "").strip() or "by_name"
    entry["permissions"] = {key: bool(value) for key, value in (values.get("permissions") or {}).items()}
    if entry["is_current_table"] and not entry["table"]:
        entry["table"] = "__CURRENT_TABLE__"
    return {"table_index": idx, "entry": entry}


def add_table_access_entry(access, entry):
    tables = ensure_table_entries(access)
    tables.append(entry)
    return {"table_index": len(tables) - 1, "entry": entry}


def delete_table_access_entry(access, table_index):
    tables = ensure_table_entries(access)
    try:
        idx = int(table_index)
    except Exception:
        idx = None
    deleted = False
    if idx is not None and 0 <= idx < len(tables):
        del tables[idx]
        deleted = True
    new_index = min(idx, len(tables) - 1) if idx is not None and tables else None
    return {"table_index": new_index, "deleted": deleted}


def rebuild_table_access(node, default_access):
    if isinstance(node, dict):
        node["table_access"] = default_access
        return default_access
    return None


def build_table_access_permission_check(nodes, get_access, entry_status):
    node_list = list(nodes or [])
    total = 0
    need_config = []
    risky = []
    for idx, node in enumerate(node_list):
        access = get_access(node) if callable(get_access) else (node or {}).get("table_access", {})
        for entry in (access or {}).get("tables", []):
            total += 1
            status = entry_status(entry) if callable(entry_status) else ""
            label = f"{idx + 1}.{(node or {}).get('type')} / {(entry or {}).get('role')} / {(entry or {}).get('table')}"
            if status in ("未绑定", "未授权"):
                need_config.append(label)
            if status == "危险写入":
                risky.append(label)
    message = f"检查完成：共 {len(node_list)} 个节点，{total} 个表角色。"
    if need_config:
        message += f"\n\n待配置：{len(need_config)} 项\n" + "\n".join(need_config[:8])
    if risky:
        message += f"\n\n危险写入：{len(risky)} 项\n" + "\n".join(risky[:8])
    if not need_config and not risky:
        message += "\n\n当前没有明显缺失或危险项。"
    return {
        "total_nodes": len(node_list),
        "total_entries": total,
        "need_config": need_config,
        "risky": risky,
        "message": message,
    }


def build_table_access_impact_preview(
    node_index,
    node,
    entry,
    fields,
    table_label,
    operation_summary,
    entry_status,
    permission_summary,
    write_mode_text,
):
    if node is None or entry is None:
        return None
    fields = list(fields or [])
    try:
        display_index = int(node_index) + 1
    except Exception:
        display_index = 1
    write_mode = write_mode_text(entry.get("write_mode", "")) if callable(write_mode_text) else entry.get("write_mode", "")
    return (
        f"节点：{display_index}.{node.get('type')} / {node.get('name', '')}\n"
        f"表角色：{entry.get('role', '')}\n"
        f"实际表：{table_label(entry) if callable(table_label) else entry.get('table', '')}\n"
        f"操作：{operation_summary(entry) if callable(operation_summary) else ''}\n"
        f"状态：{entry_status(entry) if callable(entry_status) else ''}\n"
        f"权限：{permission_summary(entry) if callable(permission_summary) else ''}\n"
        f"写入模式：{write_mode or '未设置'}\n"
        f"字段映射：{len(fields)} 个"
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
    node = current_table_access_window_node(window, state)
    if node is None:
        return
    access = window.mark_node_table_access_manual(node)
    result = save_table_access_entry(
        access,
        state.get("table_index"),
        collect_table_access_window_table_form(window, table_section),
        lambda: window.make_table_access_entry("target", ""),
    )
    idx = result["table_index"]
    state["table_index"] = idx
    refresh_table_access_window_table_tree(
        window,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        select_index=idx,
    )
    status_var.set("表角色设置已保存。")


def add_table_access_window_table_entry(
    window,
    state,
    table_section,
    field_section,
    node_tree,
    table_tree,
    field_tree,
):
    node = current_table_access_window_node(window, state)
    if node is None:
        return
    access = window.mark_node_table_access_manual(node)
    result = add_table_access_entry(
        access,
        window.make_table_access_entry(
            "target",
            "",
            permissions=window.table_permission_set(read=True),
        ),
    )
    state["table_index"] = result["table_index"]
    refresh_table_access_window_table_tree(
        window,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        select_index=state["table_index"],
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
    node = current_table_access_window_node(window, state)
    idx = state.get("table_index")
    if node is None or idx is None:
        return
    access = window.mark_node_table_access_manual(node)
    result = delete_table_access_entry(access, idx)
    state["table_index"] = result["table_index"]
    refresh_table_access_window_table_tree(
        window,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        select_index=state["table_index"],
    )
    status_var.set("表角色已删除。")


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
    node = current_table_access_window_node(window, state)
    if node is None:
        return
    if not messagebox.askyesno("重建默认映射", "将根据当前节点配置重建 table_access，并覆盖手动设置。继续吗？", parent=win):
        return
    rebuild_table_access(node, window.default_table_access_for_node(node))
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
    status_var.set("已重建默认映射。")


def check_table_access_window_permissions(window, win, status_var):
    result = build_table_access_permission_check(
        window.nodes,
        window.get_node_table_access,
        window.table_access_entry_status,
    )
    messagebox.showinfo("权限检查", result["message"], parent=win)
    status_var.set("权限检查完成。")


def preview_table_access_window_impact(window, win, state):
    node = current_table_access_window_node(window, state)
    entry = current_table_access_window_table_entry(window, state)
    message = build_table_access_impact_preview(
        state.get("node_index") or 0,
        node,
        entry,
        window.table_access_field_items(entry) if entry is not None else [],
        window.table_access_entry_table_label,
        window.table_access_operation_summary,
        window.table_access_entry_status,
        window.table_permission_summary,
        window.write_mode_display_text,
    )
    if message is None:
        messagebox.showwarning("预览影响", "请先选择节点和表角色。", parent=win)
        return
    messagebox.showinfo("预览影响", message, parent=win)


def apply_table_access_window_table_preset(window, table_section, event=None):
    preset = table_section["preset_var"].get()
    window.apply_table_access_preset_to_vars(
        preset,
        table_section["permission_vars"],
        table_section["log_only_var"],
    )
    preset_config = table_access_preset_config(
        preset,
        [key for key, _ in window.table_access_permission_items()],
    )
    if preset_config and preset_config.get("write_mode"):
        table_section["write_mode_var"].set(preset_config["write_mode"])


def save_table_access_window_field_entry(window, state, table_section, field_section, field_tree, status_var):
    entry = current_table_access_window_table_entry(window, state)
    node = current_table_access_window_node(window, state)
    if entry is None or node is None:
        return
    window.mark_node_table_access_manual(node)
    sel = field_tree.selection()
    key = selected_field_key(sel, state["field_keys"])
    upsert_field_mapping_entry(
        entry,
        key,
        field_section["source_field_var"].get(),
        field_section["target_field_var"].get(),
        field_section["source_index_var"].get(),
        field_section["target_index_var"].get(),
        "by_order" if table_section["field_mapping_mode_var"].get() == "按列顺序" else "by_name",
        {pkey: bool(var.get()) for pkey, var in field_section["field_permission_vars"].items()},
        window.make_table_access_field_key,
    )
    refresh_table_access_window_field_tree(window, state, field_section, field_tree)
    status_var.set("字段映射已保存。")


def add_table_access_window_field_entry(window, table_section, field_section, field_tree):
    reset_field_form(
        field_section["source_field_var"],
        field_section["target_field_var"],
        field_section["source_index_var"],
        field_section["target_index_var"],
        field_section["field_permission_vars"],
        write_enabled=table_section["permission_vars"]["write_table"].get(),
    )
    field_tree.selection_remove(field_tree.selection())


def delete_table_access_window_field_entry(window, state, field_section, field_tree, status_var):
    entry = current_table_access_window_table_entry(window, state)
    node = current_table_access_window_node(window, state)
    sel = field_tree.selection()
    if entry is None or node is None or not sel:
        return
    key = selected_field_key(sel, state["field_keys"])
    if key and delete_field_mapping_entry(entry, key):
        window.mark_node_table_access_manual(node)
        refresh_table_access_window_field_tree(window, state, field_section, field_tree)
        status_var.set("字段映射已删除。")


def auto_match_table_access_window_fields(window, state, field_section, field_tree, status_var):
    entry = current_table_access_window_table_entry(window, state)
    node = current_table_access_window_node(window, state)
    if entry is None or node is None:
        return
    window.mark_node_table_access_manual(node)
    count = window.auto_match_table_access_fields(state.get("node_index") or 0, entry)
    refresh_table_access_window_field_tree(window, state, field_section, field_tree)
    status_var.set(f"自动字段匹配完成：{count} 个字段。")


def auto_match_table_access_window_fields_by_order(window, state, table_section, field_section, field_tree, status_var):
    entry = current_table_access_window_table_entry(window, state)
    node = current_table_access_window_node(window, state)
    if entry is None or node is None:
        return
    window.mark_node_table_access_manual(node)
    count = window.auto_match_table_access_fields_by_order(state.get("node_index") or 0, entry)
    table_section["field_mapping_mode_var"].set("按列顺序")
    refresh_table_access_window_field_tree(window, state, field_section, field_tree)
    status_var.set(f"按列顺序字段匹配完成：{count} 个字段。")


def clear_table_access_window_fields(window, state, field_section, field_tree, status_var):
    entry = current_table_access_window_table_entry(window, state)
    node = current_table_access_window_node(window, state)
    if entry is None or node is None:
        return
    window.mark_node_table_access_manual(node)
    clear_field_mapping(entry)
    refresh_table_access_window_field_tree(window, state, field_section, field_tree)
    status_var.set("字段映射已清空。")


def create_table_access_selection_callbacks(
    window,
    state,
    table_section,
    field_section,
    node_tree,
    table_tree,
    field_tree,
    status_var,
):
    def current_node():
        return window.current_table_access_window_node(state)

    def current_table_entry():
        return window.current_table_access_window_table_entry(state)

    def refresh_field_tree():
        window.refresh_table_access_window_field_tree(state, field_section, field_tree)

    def refresh_node_tree():
        window.refresh_table_access_node_tree(node_tree, state)

    def refresh_table_tree(select_index=None):
        window.refresh_table_access_window_table_tree(
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            select_index=select_index,
        )

    def on_node_selected(event=None, force=False):
        window.on_table_access_window_node_selected(
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
            event=event,
            force=force,
        )

    def on_table_selected(event=None):
        window.on_table_access_window_table_selected(
            state,
            table_section,
            field_section,
            table_tree,
            field_tree,
            event=event,
        )

    def on_field_selected(event=None):
        window.on_table_access_window_field_selected(state, field_section, field_tree, event=event)

    return {
        "current_node": current_node,
        "current_table_entry": current_table_entry,
        "refresh_node_tree": refresh_node_tree,
        "refresh_table_tree": refresh_table_tree,
        "refresh_field_tree": refresh_field_tree,
        "on_node_selected": on_node_selected,
        "on_table_selected": on_table_selected,
        "on_field_selected": on_field_selected,
    }


def create_table_access_table_action_callbacks(
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
    def save_table_entry():
        window.save_table_access_window_table_entry(
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def add_table_entry():
        window.add_table_access_window_table_entry(
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
        )

    def delete_table_entry():
        window.delete_table_access_window_table_entry(
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def rebuild_default_access():
        window.rebuild_table_access_window_default_access(
            win,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def check_all_permissions():
        window.check_table_access_window_permissions(win, status_var)

    def preview_impact():
        window.preview_table_access_window_impact(win, state)

    def apply_table_preset(event=None):
        window.apply_table_access_window_table_preset(table_section, event=event)

    return {
        "save_table_entry": save_table_entry,
        "add_table_entry": add_table_entry,
        "delete_table_entry": delete_table_entry,
        "rebuild_default_access": rebuild_default_access,
        "check_all_permissions": check_all_permissions,
        "preview_impact": preview_impact,
        "apply_table_preset": apply_table_preset,
    }


def create_table_access_field_action_callbacks(
    window,
    state,
    table_section,
    field_section,
    field_tree,
    status_var,
):
    def save_field_entry():
        window.save_table_access_window_field_entry(state, table_section, field_section, field_tree, status_var)

    def add_field_entry():
        window.add_table_access_window_field_entry(table_section, field_section, field_tree)

    def delete_field_entry():
        window.delete_table_access_window_field_entry(state, field_section, field_tree, status_var)

    def auto_match_fields():
        window.auto_match_table_access_window_fields(state, field_section, field_tree, status_var)

    def auto_match_fields_by_order():
        window.auto_match_table_access_window_fields_by_order(state, table_section, field_section, field_tree, status_var)

    def clear_fields():
        window.clear_table_access_window_fields(state, field_section, field_tree, status_var)

    return {
        "save_field_entry": save_field_entry,
        "add_field_entry": add_field_entry,
        "delete_field_entry": delete_field_entry,
        "auto_match_fields": auto_match_fields,
        "auto_match_fields_by_order": auto_match_fields_by_order,
        "clear_fields": clear_fields,
    }


def create_table_access_window_callbacks(
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
    selection_callbacks = create_table_access_selection_callbacks(
        window,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    )
    table_callbacks = create_table_access_table_action_callbacks(
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
    field_callbacks = create_table_access_field_action_callbacks(
        window,
        state,
        table_section,
        field_section,
        field_tree,
        status_var,
    )
    callbacks = {}
    callbacks.update(selection_callbacks)
    callbacks.update(table_callbacks)
    callbacks.update(field_callbacks)
    return callbacks


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
