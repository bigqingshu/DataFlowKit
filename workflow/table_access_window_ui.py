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
