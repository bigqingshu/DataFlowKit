# -*- coding: utf-8 -*-
"""UI action helpers for AdvancedFilterWindow rule/output sections."""

import tkinter as tk
from tkinter import messagebox

from workflow.advanced_filter_window_logic import (
    add_advanced_filter_condition,
    add_advanced_filter_join_rule,
    add_advanced_filter_output_fields,
    add_all_advanced_filter_output_fields,
    clear_advanced_filter_items,
    filter_advanced_filter_valid_state,
    remove_advanced_filter_items_by_indexes,
    remove_advanced_filter_output_fields,
)


def remove_invalid_rules_and_outputs(window):
    state = filter_advanced_filter_valid_state(
        window.conditions,
        window.join_rules,
        window.output_fields,
        window.field_display_cache,
    )
    window.conditions = state["conditions"]
    window.join_rules = state["join_rules"]
    window.output_fields = state["output_fields"]

    window.refresh_conditions_tree()
    window.refresh_join_tree()
    window.refresh_output_fields_listbox()


def add_condition(window):
    field = window.filter_field_var.get().strip()
    op = window.filter_operator_var.get().strip()
    value = window.filter_value_var.get()

    if not field:
        messagebox.showwarning("提示", "请选择筛选字段。")
        return

    if op not in ["为空", "不为空"] and value == "":
        if not messagebox.askyesno("确认", "当前条件值为空，是否继续添加？"):
            return

    window.conditions = add_advanced_filter_condition(
        window.conditions,
        field,
        op,
        value,
    )

    window.refresh_conditions_tree()
    window.filter_value_var.set("")


def delete_selected_condition(window):
    selections = list(window.conditions_tree.selection())
    if not selections:
        return

    indexes = [window.conditions_tree.index(item) for item in selections]
    window.conditions = remove_advanced_filter_items_by_indexes(
        window.conditions,
        indexes,
    )

    window.refresh_conditions_tree()


def clear_conditions(window):
    window.conditions = clear_advanced_filter_items()
    window.refresh_conditions_tree()


def refresh_conditions_tree(window):
    window.conditions_tree.delete(*window.conditions_tree.get_children())
    for cond in window.conditions:
        window.conditions_tree.insert(
            "",
            tk.END,
            values=(cond["field"], cond["op"], cond["value"])
        )


def add_join_rule(window):
    left = window.join_left_var.get().strip()
    op = window.join_operator_var.get().strip()
    right = window.join_right_var.get().strip()

    if not left or not right:
        messagebox.showwarning("提示", "请选择左右匹配字段。")
        return

    if left == right:
        if not messagebox.askyesno("确认", "左右字段相同，是否仍然添加？"):
            return

    window.join_rules = add_advanced_filter_join_rule(
        window.join_rules,
        left,
        op,
        right,
    )

    window.refresh_join_tree()


def delete_selected_join_rule(window):
    selections = list(window.join_tree.selection())
    if not selections:
        return

    indexes = [window.join_tree.index(item) for item in selections]
    window.join_rules = remove_advanced_filter_items_by_indexes(
        window.join_rules,
        indexes,
    )

    window.refresh_join_tree()


def clear_join_rules(window):
    window.join_rules = clear_advanced_filter_items()
    window.refresh_join_tree()


def refresh_join_tree(window):
    window.join_tree.delete(*window.join_tree.get_children())
    for rule in window.join_rules:
        window.join_tree.insert(
            "",
            tk.END,
            values=(rule["left"], rule["op"], rule["right"])
        )


def add_output_fields(window):
    selections = list(window.available_fields_listbox.curselection())
    if not selections:
        return

    window.output_fields = add_advanced_filter_output_fields(
        window.output_fields,
        window.field_display_cache,
        selections,
    )

    window.refresh_output_fields_listbox()


def add_all_output_fields(window):
    window.output_fields = add_all_advanced_filter_output_fields(
        window.output_fields,
        window.field_display_cache,
    )

    window.refresh_output_fields_listbox()


def remove_output_fields(window):
    selections = list(window.output_fields_listbox.curselection())
    if not selections:
        return

    window.output_fields = remove_advanced_filter_output_fields(
        window.output_fields,
        selections,
    )

    window.refresh_output_fields_listbox()


def clear_output_fields(window):
    window.output_fields = []
    window.refresh_output_fields_listbox()


def refresh_output_fields_listbox(window):
    window.output_fields_listbox.delete(0, tk.END)
    for field in window.output_fields:
        window.output_fields_listbox.insert(tk.END, field)
