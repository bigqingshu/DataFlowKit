# -*- coding: utf-8 -*-
"""Selection and refresh helpers for the table-access editor window."""

from workflow.table_access_window_logic import (
    field_mapping_item,
    field_mapping_mode_display,
    field_mapping_mode_value,
    load_field_form,
    render_field_mapping_tree,
    render_table_access_tree,
)


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
                "end",
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
