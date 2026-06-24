# -*- coding: utf-8 -*-
"""UI action helpers for AdvancedFilterWindow rule/output sections."""

import tkinter as tk
from tkinter import messagebox, filedialog

from db import TableAccessManager
from shared.atomic_json_utils import atomic_write_json, load_json_with_backup
from workflow.advanced_filter_command_service import (
    apply_advanced_filter_command,
    describe_advanced_filter_state,
)
from workflow.advanced_filter_window_logic import (
    build_advanced_filter_result_records,
    eval_advanced_filter_condition,
    eval_advanced_filter_conditions,
    eval_advanced_filter_join_rule,
    eval_advanced_filter_join_rules,
    format_advanced_filter_db_value,
    get_advanced_filter_output_fields,
    load_advanced_filter_table_records,
    parse_advanced_filter_number,
    parse_positive_int_setting,
)


def _var_get(var, default=""):
    try:
        return var.get()
    except Exception:
        return default


def _var_set(var, value):
    try:
        var.set(value)
    except Exception:
        pass


def _command_state_from_window(window):
    return describe_advanced_filter_state({
        "selected_tables": window.get_selected_tables(),
        "main_table": _var_get(window.main_table_var),
        "tables_cache": getattr(window, "tables_cache", []),
        "columns_by_table": getattr(window, "columns_cache", {}),
        "field_display_cache": getattr(window, "field_display_cache", []),
        "filter_field": _var_get(window.filter_field_var),
        "join_left": _var_get(window.join_left_var),
        "join_right": _var_get(window.join_right_var),
        "conditions": getattr(window, "conditions", []),
        "join_rules": getattr(window, "join_rules", []),
        "output_fields": getattr(window, "output_fields", []),
        "logic": _var_get(window.logic_var, "AND"),
        "join_logic": _var_get(window.join_logic_var, "AND"),
        "result_limit": _var_get(window.result_limit_var, "5000"),
        "max_intermediate": _var_get(window.max_intermediate_var, "200000"),
        "save_table": _var_get(window.save_table_var),
        "preview_headers": getattr(window, "preview_headers", []),
        "preview_rows": getattr(window, "preview_rows", []),
    })


def _apply_command_state_to_window(window, state):
    window.field_display_cache = list(state.get("field_display_cache") or [])
    window.conditions = list(state.get("conditions") or [])
    window.join_rules = list(state.get("join_rules") or [])
    window.output_fields = list(state.get("output_fields") or [])
    window.preview_headers = list(state.get("preview_headers") or [])
    window.preview_rows = [list(row) for row in state.get("preview_rows") or []]
    _var_set(window.main_table_var, state.get("main_table", ""))
    _var_set(window.filter_field_var, state.get("filter_field", ""))
    _var_set(window.join_left_var, state.get("join_left", ""))
    _var_set(window.join_right_var, state.get("join_right", ""))
    _var_set(window.logic_var, state.get("logic", "AND"))
    _var_set(window.join_logic_var, state.get("join_logic", "AND"))
    _var_set(window.result_limit_var, state.get("result_limit", "5000"))
    _var_set(window.max_intermediate_var, state.get("max_intermediate", "200000"))
    _var_set(window.save_table_var, state.get("save_table", ""))


def _apply_editor_command(window, command):
    result = apply_advanced_filter_command(_command_state_from_window(window), command)
    _apply_command_state_to_window(window, result["state"])
    return result


def _first_issue_message(result, default="操作失败。"):
    for issue in result.get("issues") or []:
        message = issue.get("message")
        if message:
            return message
    return default


def _refresh_field_choice_widgets(window):
    for combo in [
        window.filter_field_combo,
        window.join_left_combo,
        window.join_right_combo
    ]:
        combo["values"] = window.field_display_cache

    window.available_fields_listbox.delete(0, tk.END)
    for field in window.field_display_cache:
        window.available_fields_listbox.insert(tk.END, field)


def _sync_selected_tables_listbox(window, selected_tables):
    window.selected_tables_listbox.delete(0, tk.END)
    for table in selected_tables or []:
        window.selected_tables_listbox.insert(tk.END, table)


def refresh_tables(window):
    try:
        window.tables_cache = window.app.get_table_names()

        window.main_table_combo["values"] = window.tables_cache
        window.add_table_combo["values"] = window.tables_cache

        if window.tables_cache and not window.main_table_var.get():
            window.main_table_var.set(window.tables_cache[0])
            window.reset_selected_tables_to_main()

        window.columns_cache = {}
        for table in window.tables_cache:
            try:
                window.columns_cache[table] = window.app.get_table_columns(table)
            except Exception:
                window.columns_cache[table] = []

        window.refresh_fields()
        window.status_var.set(f"已读取数据库表：{len(window.tables_cache)} 个。")

    except Exception as e:
        messagebox.showerror("刷新失败", str(e))


def on_main_table_selected(window, event=None):
    window.reset_selected_tables_to_main()
    window.refresh_fields()


def reset_selected_tables_to_main(window):
    table = window.main_table_var.get().strip()
    window.selected_tables_listbox.delete(0, tk.END)
    if table:
        window.selected_tables_listbox.insert(tk.END, table)


def get_selected_tables(window):
    return list(window.selected_tables_listbox.get(0, tk.END))


def get_current_selected_source_table(window):
    selections = list(window.selected_tables_listbox.curselection())
    if selections:
        return window.selected_tables_listbox.get(selections[0])

    table = window.main_table_var.get().strip()
    if table:
        return table

    table = window.add_table_var.get().strip()
    if table:
        return table

    return ""


def preview_selected_source_table(window):
    table_name = window.get_current_selected_source_table()

    if not table_name:
        messagebox.showwarning("提示", "请先选择一个需要预览的数据表。")
        return

    try:
        columns = window.columns_cache.get(table_name)
        if columns is None:
            columns = window.app.get_table_columns(table_name)
            window.columns_cache[table_name] = columns

        if not columns:
            messagebox.showwarning("提示", f"表没有字段：{table_name}")
            return

        limit = window.get_int_setting(window.result_limit_var, 5000)
        data = TableAccessManager(
            window.app.get_db_path(),
            node_type="高级筛选窗口预览",
        ).read_table(
            table_name,
            limit=limit,
        )

        window.preview_headers = list(data.get("headers", columns))
        window.preview_rows = [list(row) for row in data.get("rows", [])]

        window.refresh_preview_tree()

        window.status_var.set(
            f"已预览选中表格：{table_name}，"
            f"{len(window.preview_rows)} 行 × {len(window.preview_headers)} 列。"
            f" 当前预览行数受“预览最大行数”限制。"
        )

    except Exception as e:
        messagebox.showerror("预览表格失败", str(e))


def add_selected_table(window):
    table = window.add_table_var.get().strip()
    if not table:
        return

    current = window.get_selected_tables()
    if table not in current:
        window.selected_tables_listbox.insert(tk.END, table)

    window.refresh_fields()


def remove_selected_table(window):
    selections = list(window.selected_tables_listbox.curselection())
    if not selections:
        return

    main_table = window.main_table_var.get().strip()

    for index in reversed(selections):
        value = window.selected_tables_listbox.get(index)
        if value == main_table:
            messagebox.showwarning("提示", "主表不能从数据源列表中移除。")
            continue
        window.selected_tables_listbox.delete(index)

    window.remove_invalid_rules_and_outputs()
    window.refresh_fields()


def refresh_fields(window):
    selected_tables = window.get_selected_tables()

    for table in selected_tables:
        columns = window.columns_cache.get(table)
        if columns is None:
            try:
                columns = window.app.get_table_columns(table)
                window.columns_cache[table] = columns
            except Exception:
                columns = []

    _apply_editor_command(window, {
        "type": "refresh_fields",
        "selected_tables": selected_tables,
        "columns_by_table": window.columns_cache,
    })
    _refresh_field_choice_widgets(window)
    window.refresh_conditions_tree()
    window.refresh_join_tree()
    window.refresh_output_fields_listbox()


def remove_invalid_rules_and_outputs(window):
    _apply_editor_command(window, {"type": "filter_valid_state"})

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

    result = _apply_editor_command(window, {
        "type": "add_condition",
        "field": field,
        "op": op,
        "value": value,
        "allow_empty_value": True,
    })
    if not result["ok"]:
        messagebox.showwarning("提示", _first_issue_message(result))
        return

    window.refresh_conditions_tree()
    window.filter_value_var.set("")


def delete_selected_condition(window):
    selections = list(window.conditions_tree.selection())
    if not selections:
        return

    indexes = [window.conditions_tree.index(item) for item in selections]
    _apply_editor_command(window, {
        "type": "delete_conditions",
        "indexes": indexes,
    })

    window.refresh_conditions_tree()


def clear_conditions(window):
    _apply_editor_command(window, {"type": "clear_conditions"})
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

    result = _apply_editor_command(window, {
        "type": "add_join_rule",
        "left": left,
        "op": op,
        "right": right,
        "allow_same_field": True,
    })
    if not result["ok"]:
        messagebox.showwarning("提示", _first_issue_message(result))
        return

    window.refresh_join_tree()


def delete_selected_join_rule(window):
    selections = list(window.join_tree.selection())
    if not selections:
        return

    indexes = [window.join_tree.index(item) for item in selections]
    _apply_editor_command(window, {
        "type": "delete_join_rules",
        "indexes": indexes,
    })

    window.refresh_join_tree()


def clear_join_rules(window):
    _apply_editor_command(window, {"type": "clear_join_rules"})
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

    _apply_editor_command(window, {
        "type": "add_output_fields",
        "indexes": selections,
    })

    window.refresh_output_fields_listbox()


def add_all_output_fields(window):
    _apply_editor_command(window, {"type": "add_all_output_fields"})

    window.refresh_output_fields_listbox()


def remove_output_fields(window):
    selections = list(window.output_fields_listbox.curselection())
    if not selections:
        return

    _apply_editor_command(window, {
        "type": "remove_output_fields",
        "indexes": selections,
    })

    window.refresh_output_fields_listbox()


def clear_output_fields(window):
    _apply_editor_command(window, {"type": "clear_output_fields"})
    window.refresh_output_fields_listbox()


def refresh_output_fields_listbox(window):
    window.output_fields_listbox.delete(0, tk.END)
    for field in window.output_fields:
        window.output_fields_listbox.insert(tk.END, field)


def load_json_file_with_recovery(path, parent=None):
    data, info = load_json_with_backup(path)
    warning = info.get("warning", "")
    if warning:
        messagebox.showwarning("配置已从备份恢复", warning, parent=parent)
    return data


def format_db_value(window, value):
    return format_advanced_filter_db_value(window.app, value)


def load_table_records(window, table_name):
    columns = window.columns_cache.get(table_name)
    if columns is None:
        columns = window.app.get_table_columns(table_name)
        window.columns_cache[table_name] = columns
    return load_advanced_filter_table_records(window.app.get_db_path(), table_name, columns)


def parse_number(value):
    return parse_advanced_filter_number(value)


def eval_condition(record, cond):
    return eval_advanced_filter_condition(record, cond)


def eval_join_rule(record, rule):
    return eval_advanced_filter_join_rule(record, rule)


def eval_conditions(window, record):
    return eval_advanced_filter_conditions(record, window.conditions, window.logic_var.get())


def eval_join_rules(window, record):
    return eval_advanced_filter_join_rules(record, window.join_rules, window.join_logic_var.get())


def get_int_setting(var, default_value):
    return parse_positive_int_setting(var.get(), default_value)


def build_result_records(window):
    selected_tables = window.get_selected_tables()

    result_limit = window.get_int_setting(window.result_limit_var, 5000)
    max_intermediate = window.get_int_setting(window.max_intermediate_var, 200000)

    table_records_map = {}
    for table in selected_tables:
        table_records_map[table] = window.load_table_records(table)

    return build_advanced_filter_result_records(
        selected_tables,
        table_records_map,
        conditions=window.conditions,
        condition_logic=window.logic_var.get(),
        join_rules=window.join_rules,
        join_logic=window.join_logic_var.get(),
        result_limit=result_limit,
        max_intermediate=max_intermediate,
    )


def get_output_fields(window):
    state = _command_state_from_window(window)
    result = apply_advanced_filter_command(state, {"type": "export_template"})
    return get_advanced_filter_output_fields(
        result["state"]["output_fields"],
        result["state"]["field_display_cache"],
    )


def preview_result(window):
    try:
        selected_tables = window.get_selected_tables()
        table_records_map = {}
        for table in selected_tables:
            table_records_map[table] = window.load_table_records(table)

        result = _apply_editor_command(window, {
            "type": "build_preview",
            "table_records_map": table_records_map,
        })
        if not result["ok"]:
            messagebox.showwarning("提示", _first_issue_message(result))
            return

        window.refresh_preview_tree()

        window.status_var.set(
            f"预览完成：{len(window.preview_rows)} 行 × {len(window.preview_headers)} 列。"
            f" 当前预览行数受“预览最大行数”限制。"
        )

    except Exception as e:
        messagebox.showerror("预览失败", str(e))


def refresh_preview_tree(window):
    window.preview_tree.delete(*window.preview_tree.get_children())
    window.preview_tree["columns"] = window.preview_headers

    for col in window.preview_headers:
        window.preview_tree.heading(col, text=col)
        window.preview_tree.column(col, width=150, minwidth=80, anchor=tk.W, stretch=False)

    for row in window.preview_rows:
        window.preview_tree.insert("", tk.END, values=row)


def remove_duplicate_preview_rows(window):
    if not window.preview_headers:
        window.preview_result()
    if not window.preview_headers:
        return

    before_count = len(window.preview_rows)
    result = _apply_editor_command(window, {"type": "dedupe_preview"})
    removed = before_count - len(window.preview_rows)
    if not result["ok"]:
        messagebox.showwarning("提示", _first_issue_message(result))
        return
    window.refresh_preview_tree()
    window.status_var.set(
        f"已去除重复内容：删除 {removed} 行，剩余 {len(window.preview_rows)} 行。"
        " 判断规则：按当前预览输出整行内容去重，保留第一条。"
    )


def load_preview_to_main(window):
    if not window.preview_headers:
        messagebox.showwarning("提示", "请先预览结果。")
        return

    result = _apply_editor_command(window, {"type": "build_main_preview_snapshot"})
    if not result["ok"]:
        messagebox.showwarning("提示", _first_issue_message(result))
        return
    snapshot = result["main_preview_snapshot"]
    window.app.headers = snapshot["headers"]
    window.app.rows = snapshot["rows"]
    window.app.raw_data = snapshot["raw_data"]
    window.app.refresh_tree()
    window.app.info_var.set(
        f"已从高级筛选载入预览结果：{len(window.app.rows)} 行 × {len(window.app.headers)} 列。"
    )


def save_result_to_table(window):
    if not window.preview_headers:
        window.preview_result()

    if not window.preview_headers:
        return

    try:
        result = _apply_editor_command(window, {
            "type": "save_preview_to_table",
            "db_path": window.app.get_db_path(),
            "table_name": _var_get(window.save_table_var),
            "mode": "timestamp",
        })
        if not result["ok"]:
            messagebox.showwarning("提示", _first_issue_message(result))
            return

        saved = result.get("save_result") or {}
        table_name = saved.get("table_name") or _var_get(window.save_table_var)
        row_count = saved.get("row_count", len(window.preview_rows))

        window.status_var.set(f"保存成功：{table_name}，{row_count} 行。")
        messagebox.showinfo(
            "保存成功",
            f"筛选结果已保存到新表。\n\n表名：{table_name}\n行数：{row_count}"
        )

        window.refresh_tables()

    except Exception as e:
        messagebox.showerror("保存失败", str(e))


def export_template_data(window):
    result = _apply_editor_command(window, {"type": "export_template"})
    return result["template"]


def apply_template_data(window, data):
    selected_tables = [
        table for table in data.get("selected_tables", [])
        if table in getattr(window, "tables_cache", [])
    ]
    if not selected_tables:
        main_table = data.get("main_table", "")
        if main_table in getattr(window, "tables_cache", []):
            selected_tables = [main_table]
    for table in selected_tables:
        if table not in window.columns_cache:
            try:
                window.columns_cache[table] = window.app.get_table_columns(table)
            except Exception:
                window.columns_cache[table] = []

    result = _apply_editor_command(window, {
        "type": "apply_template",
        "template": data,
    })
    if not result["ok"]:
        messagebox.showwarning("提示", _first_issue_message(result))
        return
    _sync_selected_tables_listbox(window, result["state"].get("selected_tables") or [])
    _refresh_field_choice_widgets(window)

    window.refresh_conditions_tree()
    window.refresh_join_tree()
    window.refresh_output_fields_listbox()


def save_template(window):
    path = filedialog.asksaveasfilename(
        title="保存筛选模板",
        defaultextension=".json",
        filetypes=[
            ("JSON 文件", "*.json"),
            ("所有文件", "*.*")
        ]
    )
    if not path:
        return

    try:
        data = window.export_template_data()
        atomic_write_json(path, data)

        window.status_var.set(f"筛选模板已保存：{path}")

    except Exception as e:
        messagebox.showerror("保存模板失败", str(e))


def load_template(window):
    path = filedialog.askopenfilename(
        title="载入筛选模板",
        filetypes=[
            ("JSON 文件", "*.json"),
            ("所有文件", "*.*")
        ]
    )
    if not path:
        return

    try:
        data = load_json_file_with_recovery(path, parent=window.window)

        window.apply_template_data(data)
        window.status_var.set(f"筛选模板已载入：{path}")

    except Exception as e:
        messagebox.showerror("载入模板失败", str(e))
