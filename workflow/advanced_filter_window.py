# -*- coding: utf-8 -*-
"""Advanced filter / data matching window."""

import tkinter as tk
from tkinter import ttk
from datetime import datetime

from workflow import advanced_filter_window_actions as advanced_filter_actions


def load_json_file_with_recovery(path, parent=None):
    return advanced_filter_actions.load_json_file_with_recovery(path, parent=parent)


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
        return advanced_filter_actions.refresh_tables(self)

    def on_main_table_selected(self, event=None):
        return advanced_filter_actions.on_main_table_selected(self, event=event)

    def reset_selected_tables_to_main(self):
        return advanced_filter_actions.reset_selected_tables_to_main(self)

    def get_selected_tables(self):
        return advanced_filter_actions.get_selected_tables(self)

    def get_current_selected_source_table(self):
        return advanced_filter_actions.get_current_selected_source_table(self)

    def preview_selected_source_table(self):
        return advanced_filter_actions.preview_selected_source_table(self)

    def add_selected_table(self):
        return advanced_filter_actions.add_selected_table(self)

    def remove_selected_table(self):
        return advanced_filter_actions.remove_selected_table(self)

    def refresh_fields(self):
        return advanced_filter_actions.refresh_fields(self)

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
        return advanced_filter_actions.format_db_value(self, value)

    def load_table_records(self, table_name):
        return advanced_filter_actions.load_table_records(self, table_name)

    def parse_number(self, value):
        return advanced_filter_actions.parse_number(value)

    def eval_condition(self, record, cond):
        return advanced_filter_actions.eval_condition(record, cond)

    def eval_join_rule(self, record, rule):
        return advanced_filter_actions.eval_join_rule(record, rule)

    def eval_conditions(self, record):
        return advanced_filter_actions.eval_conditions(self, record)

    def eval_join_rules(self, record):
        return advanced_filter_actions.eval_join_rules(self, record)

    def get_int_setting(self, var, default_value):
        return advanced_filter_actions.get_int_setting(var, default_value)

    def build_result_records(self):
        return advanced_filter_actions.build_result_records(self)

    def get_output_fields(self):
        return advanced_filter_actions.get_output_fields(self)

    def preview_result(self):
        return advanced_filter_actions.preview_result(self)

    def refresh_preview_tree(self):
        return advanced_filter_actions.refresh_preview_tree(self)

    def remove_duplicate_preview_rows(self):
        return advanced_filter_actions.remove_duplicate_preview_rows(self)

    def load_preview_to_main(self):
        return advanced_filter_actions.load_preview_to_main(self)

    def save_result_to_table(self):
        return advanced_filter_actions.save_result_to_table(self)

    def export_template_data(self):
        return advanced_filter_actions.export_template_data(self)

    def apply_template_data(self, data):
        return advanced_filter_actions.apply_template_data(self, data)

    def save_template(self):
        return advanced_filter_actions.save_template(self)

    def load_template(self):
        return advanced_filter_actions.load_template(self)
