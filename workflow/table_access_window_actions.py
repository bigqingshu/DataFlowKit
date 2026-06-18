# -*- coding: utf-8 -*-
"""Action handlers for the table-access editor window."""

from tkinter import messagebox

from workflow.table_access_window_logic import (
    add_table_access_entry,
    build_table_access_impact_preview,
    build_table_access_permission_check,
    clear_field_mapping,
    delete_field_mapping_entry,
    delete_table_access_entry,
    rebuild_table_access,
    reset_field_form,
    save_table_access_entry,
    selected_field_key,
    table_access_preset_config,
    upsert_field_mapping_entry,
)
from workflow.table_access_window_ui import (
    collect_table_access_window_table_form,
    current_table_access_window_node,
    current_table_access_window_table_entry,
    refresh_table_access_window_field_tree,
    refresh_table_access_window_table_tree,
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
