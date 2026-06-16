# -*- coding: utf-8 -*-
"""Small UI/data helpers for the table-access editor window."""

from workflow.table_access_precheck import table_access_field_items


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
