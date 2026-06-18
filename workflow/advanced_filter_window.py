# -*- coding: utf-8 -*-
"""Advanced filter / data matching window."""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

from db import TableAccessManager
from shared.atomic_json_utils import atomic_write_json, load_json_with_backup
from workflow import advanced_filter_window_actions as advanced_filter_actions
from workflow.advanced_filter_window_logic import (
    build_advanced_filter_field_display_cache as workflow_build_advanced_filter_field_display_cache,
    build_advanced_filter_main_preview_snapshot as workflow_build_advanced_filter_main_preview_snapshot,
    build_advanced_filter_preview_rows as workflow_build_advanced_filter_preview_rows,
    build_advanced_filter_template_data as workflow_build_advanced_filter_template_data,
    build_advanced_filter_result_records as workflow_build_advanced_filter_result_records,
    dedupe_advanced_filter_preview_rows as workflow_dedupe_advanced_filter_preview_rows,
    eval_advanced_filter_condition as workflow_eval_advanced_filter_condition,
    eval_advanced_filter_conditions as workflow_eval_advanced_filter_conditions,
    eval_advanced_filter_join_rule as workflow_eval_advanced_filter_join_rule,
    eval_advanced_filter_join_rules as workflow_eval_advanced_filter_join_rules,
    format_advanced_filter_db_value as workflow_format_advanced_filter_db_value,
    get_advanced_filter_output_fields as workflow_get_advanced_filter_output_fields,
    load_advanced_filter_table_records as workflow_load_advanced_filter_table_records,
    normalize_advanced_filter_template_data as workflow_normalize_advanced_filter_template_data,
    normalize_advanced_filter_save_table_name as workflow_normalize_advanced_filter_save_table_name,
    parse_advanced_filter_number as workflow_parse_advanced_filter_number,
    parse_positive_int_setting as workflow_parse_positive_int_setting,
    select_advanced_filter_combo_defaults as workflow_select_advanced_filter_combo_defaults,
    select_advanced_filter_template_tables as workflow_select_advanced_filter_template_tables,
)


def load_json_file_with_recovery(path, parent=None):
    data, info = load_json_with_backup(path)
    warning = info.get("warning", "")
    if warning:
        messagebox.showwarning("配置已从备份恢复", warning, parent=parent)
    return data


class AdvancedFilterWindow:
    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("高级筛选 / 数据匹配")
        self.window.geometry("1380x820")
        self.window.transient(app.root)

        self.tables_cache = []
        self.columns_cache = {}
        self.field_display_cache = []

        self.conditions = []
        self.join_rules = []
        self.output_fields = []
        self.preview_headers = []
        self.preview_rows = []

        self.main_table_var = tk.StringVar()
        self.add_table_var = tk.StringVar()

        self.filter_field_var = tk.StringVar()
        self.filter_operator_var = tk.StringVar(value="包含")
        self.filter_value_var = tk.StringVar()
        self.logic_var = tk.StringVar(value="AND")

        self.join_left_var = tk.StringVar()
        self.join_operator_var = tk.StringVar(value="等于")
        self.join_right_var = tk.StringVar()
        self.join_logic_var = tk.StringVar(value="AND")

        self.result_limit_var = tk.StringVar(value="5000")
        self.max_intermediate_var = tk.StringVar(value="200000")
        self.save_table_var = tk.StringVar(
            value="筛选结果_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        )

        self.status_var = tk.StringVar(value="请选择数据源。")

        self.build_ui()
        self.refresh_tables()

    def build_ui(self):
        main = ttk.Frame(self.window, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(main)
        top.pack(fill=tk.X)

        ttk.Label(top, text="数据库：").pack(side=tk.LEFT)
        ttk.Label(top, text=self.app.get_db_path()).pack(side=tk.LEFT, padx=4)

        ttk.Button(top, text="刷新表/字段", command=self.refresh_tables).pack(side=tk.RIGHT, padx=4)
        ttk.Button(top, text="保存筛选模板", command=self.save_template).pack(side=tk.RIGHT, padx=4)
        ttk.Button(top, text="载入筛选模板", command=self.load_template).pack(side=tk.RIGHT, padx=4)

        body = ttk.Panedwindow(main, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, pady=8)

        left_panel = ttk.Frame(body, padding=4)
        right_panel = ttk.Frame(body, padding=4)

        body.add(left_panel, weight=1)
        body.add(right_panel, weight=2)

        self.build_left_panel(left_panel)
        self.build_right_panel(right_panel)

        ttk.Label(main, textvariable=self.status_var, padding=4).pack(fill=tk.X)

    def build_left_panel(self, parent):
        source_frame = ttk.LabelFrame(parent, text="1. 数据源选择", padding=6)
        source_frame.pack(fill=tk.X, pady=4)

        row1 = ttk.Frame(source_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="主表：", width=8).pack(side=tk.LEFT)
        self.main_table_combo = ttk.Combobox(row1, textvariable=self.main_table_var, state="readonly", width=30)
        self.main_table_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.main_table_combo.bind("<<ComboboxSelected>>", self.on_main_table_selected)

        row2 = ttk.Frame(source_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="添加表：", width=8).pack(side=tk.LEFT)
        self.add_table_combo = ttk.Combobox(row2, textvariable=self.add_table_var, state="readonly", width=30)
        self.add_table_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row2, text="添加", command=self.add_selected_table).pack(side=tk.LEFT, padx=4)

        row3 = ttk.Frame(source_frame)
        row3.pack(fill=tk.BOTH, expand=True, pady=2)

        self.selected_tables_listbox = tk.Listbox(row3, height=5, exportselection=False)
        self.selected_tables_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        table_scroll = ttk.Scrollbar(row3, orient=tk.VERTICAL, command=self.selected_tables_listbox.yview)
        table_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.selected_tables_listbox.configure(yscrollcommand=table_scroll.set)

        row4 = ttk.Frame(source_frame)
        row4.pack(fill=tk.X, pady=2)
        ttk.Button(row4, text="移除选中表", command=self.remove_selected_table).pack(side=tk.LEFT, padx=2)
        ttk.Button(row4, text="刷新字段列表", command=self.refresh_fields).pack(side=tk.LEFT, padx=2)
        ttk.Button(row4, text="预览选中表格", command=self.preview_selected_source_table).pack(side=tk.LEFT, padx=2)

        filter_frame = ttk.LabelFrame(parent, text="2. 条件筛选", padding=6)
        filter_frame.pack(fill=tk.BOTH, expand=True, pady=4)

        cond_add = ttk.Frame(filter_frame)
        cond_add.pack(fill=tk.X, pady=2)

        ttk.Label(cond_add, text="字段").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(cond_add, text="操作").grid(row=0, column=1, sticky=tk.W)
        ttk.Label(cond_add, text="值").grid(row=0, column=2, sticky=tk.W)

        self.filter_field_combo = ttk.Combobox(cond_add, textvariable=self.filter_field_var, state="readonly", width=24)
        self.filter_field_combo.grid(row=1, column=0, padx=2, pady=2)

        self.filter_operator_combo = ttk.Combobox(
            cond_add,
            textvariable=self.filter_operator_var,
            state="readonly",
            width=12,
            values=[
                "等于", "不等于", "包含", "不包含",
                "开头是", "结尾是",
                "大于", "小于", "大于等于", "小于等于",
                "为空", "不为空",
                "忽略大小写等于", "忽略大小写包含"
            ]
        )
        self.filter_operator_combo.grid(row=1, column=1, padx=2, pady=2)

        ttk.Entry(cond_add, textvariable=self.filter_value_var, width=18).grid(row=1, column=2, padx=2, pady=2)
        ttk.Button(cond_add, text="添加条件", command=self.add_condition).grid(row=1, column=3, padx=2, pady=2)

        logic_row = ttk.Frame(filter_frame)
        logic_row.pack(fill=tk.X, pady=2)
        ttk.Label(logic_row, text="多条件关系：").pack(side=tk.LEFT)
        ttk.Combobox(
            logic_row,
            textvariable=self.logic_var,
            state="readonly",
            width=8,
            values=["AND", "OR"]
        ).pack(side=tk.LEFT)

        self.conditions_tree = ttk.Treeview(
            filter_frame,
            columns=("field", "op", "value"),
            show="headings",
            height=8
        )
        self.conditions_tree.heading("field", text="字段")
        self.conditions_tree.heading("op", text="操作")
        self.conditions_tree.heading("value", text="值")
        self.conditions_tree.column("field", width=170, stretch=False)
        self.conditions_tree.column("op", width=90, stretch=False)
        self.conditions_tree.column("value", width=130, stretch=False)
        self.conditions_tree.pack(fill=tk.BOTH, expand=True, pady=2)

        cond_buttons = ttk.Frame(filter_frame)
        cond_buttons.pack(fill=tk.X, pady=2)
        ttk.Button(cond_buttons, text="删除选中条件", command=self.delete_selected_condition).pack(side=tk.LEFT, padx=2)
        ttk.Button(cond_buttons, text="清空条件", command=self.clear_conditions).pack(side=tk.LEFT, padx=2)

        join_frame = ttk.LabelFrame(parent, text="3. 多表匹配规则", padding=6)
        join_frame.pack(fill=tk.BOTH, expand=True, pady=4)

        join_add = ttk.Frame(join_frame)
        join_add.pack(fill=tk.X, pady=2)

        # 匹配关系放在“左字段”上方同一行，避免单独占用下方空间
        ttk.Label(join_add, text="匹配关系").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(join_add, text="左字段").grid(row=0, column=1, sticky=tk.W)
        ttk.Label(join_add, text="规则").grid(row=0, column=2, sticky=tk.W)
        ttk.Label(join_add, text="右字段").grid(row=0, column=3, sticky=tk.W)

        ttk.Combobox(
            join_add,
            textvariable=self.join_logic_var,
            state="readonly",
            width=8,
            values=["AND", "OR"]
        ).grid(row=1, column=0, padx=2, pady=2)

        self.join_left_combo = ttk.Combobox(join_add, textvariable=self.join_left_var, state="readonly", width=22)
        self.join_left_combo.grid(row=1, column=1, padx=2, pady=2)

        self.join_operator_combo = ttk.Combobox(
            join_add,
            textvariable=self.join_operator_var,
            state="readonly",
            width=14,
            values=["等于", "不等于", "左包含右", "右包含左", "双向包含"]
        )
        self.join_operator_combo.grid(row=1, column=2, padx=2, pady=2)

        self.join_right_combo = ttk.Combobox(join_add, textvariable=self.join_right_var, state="readonly", width=22)
        self.join_right_combo.grid(row=1, column=3, padx=2, pady=2)

        ttk.Button(join_add, text="添加匹配", command=self.add_join_rule).grid(row=1, column=4, padx=2, pady=2)
        ttk.Label(join_add, text="AND=所有匹配规则都满足；OR=任意一条匹配规则满足。", foreground="gray").grid(row=2, column=0, columnspan=5, sticky=tk.W, padx=2, pady=(0, 2))

        self.join_tree = ttk.Treeview(
            join_frame,
            columns=("left", "op", "right"),
            show="headings",
            height=6
        )
        self.join_tree.heading("left", text="左字段")
        self.join_tree.heading("op", text="规则")
        self.join_tree.heading("right", text="右字段")
        self.join_tree.column("left", width=155, stretch=False)
        self.join_tree.column("op", width=85, stretch=False)
        self.join_tree.column("right", width=155, stretch=False)
        self.join_tree.pack(fill=tk.BOTH, expand=True, pady=2)

        join_buttons = ttk.Frame(join_frame)
        join_buttons.pack(fill=tk.X, pady=2)
        ttk.Button(join_buttons, text="删除选中匹配", command=self.delete_selected_join_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(join_buttons, text="清空匹配规则", command=self.clear_join_rules).pack(side=tk.LEFT, padx=2)

    def build_right_panel(self, parent):
        output_frame = ttk.LabelFrame(parent, text="4. 输出字段选择", padding=6)
        output_frame.pack(fill=tk.X, pady=4)

        output_body = ttk.Frame(output_frame)
        output_body.pack(fill=tk.BOTH, expand=True)

        left_box = ttk.Frame(output_body)
        left_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)

        ttk.Label(left_box, text="可用字段").pack(anchor=tk.W)
        self.available_fields_listbox = tk.Listbox(left_box, selectmode=tk.EXTENDED, height=8, exportselection=False)
        self.available_fields_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        available_scroll = ttk.Scrollbar(left_box, orient=tk.VERTICAL, command=self.available_fields_listbox.yview)
        available_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.available_fields_listbox.configure(yscrollcommand=available_scroll.set)

        mid_buttons = ttk.Frame(output_body)
        mid_buttons.pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Button(mid_buttons, text="添加 >", command=self.add_output_fields).pack(pady=3)
        ttk.Button(mid_buttons, text="全部添加 >>", command=self.add_all_output_fields).pack(pady=3)
        ttk.Button(mid_buttons, text="< 删除", command=self.remove_output_fields).pack(pady=3)
        ttk.Button(mid_buttons, text="清空", command=self.clear_output_fields).pack(pady=3)

        right_box = ttk.Frame(output_body)
        right_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)

        ttk.Label(right_box, text="输出字段").pack(anchor=tk.W)
        self.output_fields_listbox = tk.Listbox(right_box, selectmode=tk.EXTENDED, height=8, exportselection=False)
        self.output_fields_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        output_scroll = ttk.Scrollbar(right_box, orient=tk.VERTICAL, command=self.output_fields_listbox.yview)
        output_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.output_fields_listbox.configure(yscrollcommand=output_scroll.set)

        setting_frame = ttk.LabelFrame(parent, text="5. 预览与保存", padding=6)
        setting_frame.pack(fill=tk.X, pady=4)

        row1 = ttk.Frame(setting_frame)
        row1.pack(fill=tk.X, pady=2)

        ttk.Label(row1, text="预览最大行数：").pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.result_limit_var, width=10).pack(side=tk.LEFT, padx=2)

        ttk.Label(row1, text="中间组合上限：").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Entry(row1, textvariable=self.max_intermediate_var, width=12).pack(side=tk.LEFT, padx=2)

        ttk.Button(row1, text="预览结果", command=self.preview_result).pack(side=tk.LEFT, padx=8)
        ttk.Button(row1, text="去除重复内容", command=self.remove_duplicate_preview_rows).pack(side=tk.LEFT, padx=4)
        ttk.Button(row1, text="载入主界面预览", command=self.load_preview_to_main).pack(side=tk.LEFT, padx=4)

        row2 = ttk.Frame(setting_frame)
        row2.pack(fill=tk.X, pady=2)

        ttk.Label(row2, text="保存为新表：").pack(side=tk.LEFT)
        ttk.Entry(row2, textvariable=self.save_table_var, width=35).pack(side=tk.LEFT, padx=2)
        ttk.Button(row2, text="保存结果到新表", command=self.save_result_to_table).pack(side=tk.LEFT, padx=8)

        preview_frame = ttk.LabelFrame(parent, text="6. 筛选结果预览", padding=6)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=4)

        self.preview_tree = ttk.Treeview(preview_frame, show="headings")
        y_scroll = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.preview_tree.yview)
        x_scroll = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=self.preview_tree.xview)
        self.preview_tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.preview_tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)

    def refresh_tables(self):
        try:
            self.tables_cache = self.app.get_table_names()

            self.main_table_combo["values"] = self.tables_cache
            self.add_table_combo["values"] = self.tables_cache

            if self.tables_cache and not self.main_table_var.get():
                self.main_table_var.set(self.tables_cache[0])
                self.reset_selected_tables_to_main()

            self.columns_cache = {}
            for table in self.tables_cache:
                try:
                    self.columns_cache[table] = self.app.get_table_columns(table)
                except Exception:
                    self.columns_cache[table] = []

            self.refresh_fields()
            self.status_var.set(f"已读取数据库表：{len(self.tables_cache)} 个。")

        except Exception as e:
            messagebox.showerror("刷新失败", str(e))

    def on_main_table_selected(self, event=None):
        self.reset_selected_tables_to_main()
        self.refresh_fields()

    def reset_selected_tables_to_main(self):
        table = self.main_table_var.get().strip()
        self.selected_tables_listbox.delete(0, tk.END)
        if table:
            self.selected_tables_listbox.insert(tk.END, table)

    def get_selected_tables(self):
        return list(self.selected_tables_listbox.get(0, tk.END))

    def get_current_selected_source_table(self):
        """
        获取“1. 数据源选择”区域中当前要预览的表。
        优先使用列表框中选中的表；如果没有选中，则使用主表。
        """
        selections = list(self.selected_tables_listbox.curselection())
        if selections:
            return self.selected_tables_listbox.get(selections[0])

        table = self.main_table_var.get().strip()
        if table:
            return table

        table = self.add_table_var.get().strip()
        if table:
            return table

        return ""

    def preview_selected_source_table(self):
        """
        在右侧“筛选结果预览”区域预览数据源列表中当前选中的表。
        这个预览不会改变筛选条件，也不会执行多表匹配，只是快速查看原表内容。
        """
        table_name = self.get_current_selected_source_table()

        if not table_name:
            messagebox.showwarning("提示", "请先选择一个需要预览的数据表。")
            return

        try:
            columns = self.columns_cache.get(table_name)
            if columns is None:
                columns = self.app.get_table_columns(table_name)
                self.columns_cache[table_name] = columns

            if not columns:
                messagebox.showwarning("提示", f"表没有字段：{table_name}")
                return

            limit = self.get_int_setting(self.result_limit_var, 5000)
            data = TableAccessManager(
                self.app.get_db_path(),
                node_type="高级筛选窗口预览",
            ).read_table(
                table_name,
                limit=limit,
            )

            self.preview_headers = list(data.get("headers", columns))
            self.preview_rows = [list(row) for row in data.get("rows", [])]

            self.refresh_preview_tree()

            self.status_var.set(
                f"已预览选中表格：{table_name}，"
                f"{len(self.preview_rows)} 行 × {len(self.preview_headers)} 列。"
                f" 当前预览行数受“预览最大行数”限制。"
            )

        except Exception as e:
            messagebox.showerror("预览表格失败", str(e))

    def add_selected_table(self):
        table = self.add_table_var.get().strip()
        if not table:
            return

        current = self.get_selected_tables()
        if table not in current:
            self.selected_tables_listbox.insert(tk.END, table)

        self.refresh_fields()

    def remove_selected_table(self):
        selections = list(self.selected_tables_listbox.curselection())
        if not selections:
            return

        main_table = self.main_table_var.get().strip()

        for index in reversed(selections):
            value = self.selected_tables_listbox.get(index)
            if value == main_table:
                messagebox.showwarning("提示", "主表不能从数据源列表中移除。")
                continue
            self.selected_tables_listbox.delete(index)

        self.remove_invalid_rules_and_outputs()
        self.refresh_fields()

    def refresh_fields(self):
        selected_tables = self.get_selected_tables()

        for table in selected_tables:
            columns = self.columns_cache.get(table)
            if columns is None:
                try:
                    columns = self.app.get_table_columns(table)
                    self.columns_cache[table] = columns
                except Exception:
                    columns = []

        self.field_display_cache = workflow_build_advanced_filter_field_display_cache(
            selected_tables,
            self.columns_cache,
        )

        for combo in [
            self.filter_field_combo,
            self.join_left_combo,
            self.join_right_combo
        ]:
            combo["values"] = self.field_display_cache

        self.available_fields_listbox.delete(0, tk.END)
        for field in self.field_display_cache:
            self.available_fields_listbox.insert(tk.END, field)

        defaults = workflow_select_advanced_filter_combo_defaults(
            self.field_display_cache,
            self.filter_field_var.get(),
            self.join_left_var.get(),
            self.join_right_var.get(),
        )
        self.filter_field_var.set(defaults["filter_field"])
        self.join_left_var.set(defaults["join_left"])
        self.join_right_var.set(defaults["join_right"])

        self.remove_invalid_rules_and_outputs()

    def remove_invalid_rules_and_outputs(self):
        return advanced_filter_actions.remove_invalid_rules_and_outputs(self)

    def add_condition(self):
        return advanced_filter_actions.add_condition(self)

    def delete_selected_condition(self):
        return advanced_filter_actions.delete_selected_condition(self)

    def clear_conditions(self):
        return advanced_filter_actions.clear_conditions(self)

    def refresh_conditions_tree(self):
        return advanced_filter_actions.refresh_conditions_tree(self)

    def add_join_rule(self):
        return advanced_filter_actions.add_join_rule(self)

    def delete_selected_join_rule(self):
        return advanced_filter_actions.delete_selected_join_rule(self)

    def clear_join_rules(self):
        return advanced_filter_actions.clear_join_rules(self)

    def refresh_join_tree(self):
        return advanced_filter_actions.refresh_join_tree(self)

    def add_output_fields(self):
        return advanced_filter_actions.add_output_fields(self)

    def add_all_output_fields(self):
        return advanced_filter_actions.add_all_output_fields(self)

    def remove_output_fields(self):
        return advanced_filter_actions.remove_output_fields(self)

    def clear_output_fields(self):
        return advanced_filter_actions.clear_output_fields(self)

    def refresh_output_fields_listbox(self):
        return advanced_filter_actions.refresh_output_fields_listbox(self)

    def format_db_value(self, value):
        return workflow_format_advanced_filter_db_value(self.app, value)

    def load_table_records(self, table_name):
        columns = self.columns_cache.get(table_name)
        if columns is None:
            columns = self.app.get_table_columns(table_name)
            self.columns_cache[table_name] = columns
        return workflow_load_advanced_filter_table_records(self.app.get_db_path(), table_name, columns)

    def parse_number(self, value):
        return workflow_parse_advanced_filter_number(value)

    def eval_condition(self, record, cond):
        return workflow_eval_advanced_filter_condition(record, cond)

    def eval_join_rule(self, record, rule):
        return workflow_eval_advanced_filter_join_rule(record, rule)

    def eval_conditions(self, record):
        return workflow_eval_advanced_filter_conditions(record, self.conditions, self.logic_var.get())

    def eval_join_rules(self, record):
        return workflow_eval_advanced_filter_join_rules(record, self.join_rules, self.join_logic_var.get())

    def get_int_setting(self, var, default_value):
        return workflow_parse_positive_int_setting(var.get(), default_value)

    def build_result_records(self):
        selected_tables = self.get_selected_tables()

        result_limit = self.get_int_setting(self.result_limit_var, 5000)
        max_intermediate = self.get_int_setting(self.max_intermediate_var, 200000)

        table_records_map = {}
        for table in selected_tables:
            table_records_map[table] = self.load_table_records(table)

        return workflow_build_advanced_filter_result_records(
            selected_tables,
            table_records_map,
            conditions=self.conditions,
            condition_logic=self.logic_var.get(),
            join_rules=self.join_rules,
            join_logic=self.join_logic_var.get(),
            result_limit=result_limit,
            max_intermediate=max_intermediate,
        )

    def get_output_fields(self):
        return workflow_get_advanced_filter_output_fields(
            self.output_fields,
            self.field_display_cache,
        )

    def preview_result(self):
        try:
            fields = self.get_output_fields()
            if not fields:
                messagebox.showwarning("提示", "没有可输出字段，请先选择数据源。")
                return

            records = self.build_result_records()

            self.preview_headers = fields
            self.preview_rows = workflow_build_advanced_filter_preview_rows(records, fields)

            self.refresh_preview_tree()

            self.status_var.set(
                f"预览完成：{len(self.preview_rows)} 行 × {len(self.preview_headers)} 列。"
                f" 当前预览行数受“预览最大行数”限制。"
            )

        except Exception as e:
            messagebox.showerror("预览失败", str(e))

    def refresh_preview_tree(self):
        self.preview_tree.delete(*self.preview_tree.get_children())
        self.preview_tree["columns"] = self.preview_headers

        for col in self.preview_headers:
            self.preview_tree.heading(col, text=col)
            self.preview_tree.column(col, width=150, minwidth=80, anchor=tk.W, stretch=False)

        for row in self.preview_rows:
            self.preview_tree.insert("", tk.END, values=row)

    def remove_duplicate_preview_rows(self):
        if not self.preview_headers:
            self.preview_result()
        if not self.preview_headers:
            return

        result = workflow_dedupe_advanced_filter_preview_rows(self.preview_rows)
        self.preview_rows = result["rows"]
        self.refresh_preview_tree()
        self.status_var.set(
            f"已去除重复内容：删除 {result['removed']} 行，剩余 {len(self.preview_rows)} 行。"
            " 判断规则：按当前预览输出整行内容去重，保留第一条。"
        )

    def load_preview_to_main(self):
        if not self.preview_headers:
            messagebox.showwarning("提示", "请先预览结果。")
            return

        snapshot = workflow_build_advanced_filter_main_preview_snapshot(
            self.preview_headers,
            self.preview_rows,
        )
        self.app.headers = snapshot["headers"]
        self.app.rows = snapshot["rows"]
        self.app.raw_data = snapshot["raw_data"]
        self.app.refresh_tree()
        self.app.info_var.set(
            f"已从高级筛选载入预览结果：{len(self.app.rows)} 行 × {len(self.app.headers)} 列。"
        )

    def save_result_to_table(self):
        if not self.preview_headers:
            self.preview_result()

        if not self.preview_headers:
            return

        save_name = workflow_normalize_advanced_filter_save_table_name(self.save_table_var.get())
        if not save_name:
            messagebox.showwarning("提示", "请填写保存的新表名。")
            return

        try:
            table_name, row_count = self.app.save_rows_to_sqlite_table(
                table_name_raw=save_name,
                headers=self.preview_headers,
                rows=self.preview_rows,
                recreate=False
            )

            self.status_var.set(f"保存成功：{table_name}，{row_count} 行。")
            messagebox.showinfo(
                "保存成功",
                f"筛选结果已保存到新表。\n\n表名：{table_name}\n行数：{row_count}"
            )

            self.refresh_tables()

        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def export_template_data(self):
        return workflow_build_advanced_filter_template_data(
            self.main_table_var.get(),
            self.get_selected_tables(),
            self.conditions,
            self.logic_var.get(),
            self.join_logic_var.get(),
            self.join_rules,
            self.output_fields,
            self.result_limit_var.get(),
            self.max_intermediate_var.get(),
            self.save_table_var.get(),
        )

    def apply_template_data(self, data):
        main_table = data.get("main_table", "")

        if main_table:
            self.main_table_var.set(main_table)

        self.selected_tables_listbox.delete(0, tk.END)
        for table in workflow_select_advanced_filter_template_tables(data, self.tables_cache):
            self.selected_tables_listbox.insert(tk.END, table)

        self.refresh_fields()

        state = workflow_normalize_advanced_filter_template_data(
            data,
            self.tables_cache,
            self.field_display_cache,
            current_save_table=self.save_table_var.get(),
        )
        self.conditions = state["conditions"]
        self.join_rules = state["join_rules"]
        self.output_fields = state["output_fields"]
        self.logic_var.set(state["logic"])
        self.join_logic_var.set(state["join_logic"])
        self.result_limit_var.set(state["result_limit"])
        self.max_intermediate_var.set(state["max_intermediate"])
        self.save_table_var.set(state["save_table"])

        self.refresh_conditions_tree()
        self.refresh_join_tree()
        self.refresh_output_fields_listbox()

    def save_template(self):
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
            data = self.export_template_data()
            atomic_write_json(path, data)

            self.status_var.set(f"筛选模板已保存：{path}")

        except Exception as e:
            messagebox.showerror("保存模板失败", str(e))

    def load_template(self):
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
            data = load_json_file_with_recovery(path, parent=self.window)

            self.apply_template_data(data)
            self.status_var.set(f"筛选模板已载入：{path}")

        except Exception as e:
            messagebox.showerror("载入模板失败", str(e))
