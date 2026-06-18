# -*- coding: utf-8 -*-
"""Launcher/orchestration for the table-access editor window."""

import tkinter as tk
from tkinter import ttk


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
