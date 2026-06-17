# -*- coding: utf-8 -*-
"""
剪贴板表格解析器 - SQLite保存版 + 高级筛选/数据匹配窗口

功能概览：
1. 从 Windows 剪贴板读取 Excel/WPS/网页表格数据。
2. 在 Tkinter GUI 中预览、编辑、保存到 SQLite。
3. 下拉选择 SQLite 表后，可自动加载数据库表数据。
4. 新增“高级筛选 / 数据匹配”窗口：
   - 支持选择一个或多个 SQLite 表作为数据源。
   - 支持多条件筛选：等于、不等于、包含、大于、小于、为空等。
   - 支持多表匹配规则：字段相等、字段包含等。
   - 支持选择输出字段。
   - 支持预览筛选结果。
   - 支持保存筛选结果为新表。
   - 支持保存/载入筛选模板 JSON。
5. 新增“批量替换 / 数据处理”窗口：
   - 支持按字段进行局部字符串替换或整格替换。
   - 支持替换前预览、执行替换、撤销上一次替换。
   - 支持保存/载入替换规则模板 JSON。
6. 新增主界面“导出为 xlsx”按钮，可导出当前预览数据。
7. 新增“数据提取 / 字段生成”窗口：
   - 支持 Python 正则提取、固定位置提取、按分隔符提取、关键字之间提取等。
   - 支持预览、执行、撤销、生成新字段、覆盖源字段、保存/载入规则模板。
8. 新增“合并列 / 生成新列”窗口：
   - 支持从字段池添加字段到合并顺序列表。
   - 支持上移、下移、删除、清空字段顺序。
   - 支持每两列之间设置不同连接符，也支持自定义连接符和 {换行符}/{制表符} 等特殊占位符。
   - 支持预览、执行、撤销、保存/载入合并模板。
9. 新增“计划 / 工作流处理”窗口：
   - 支持把批量替换、数据提取、合并列、高级筛选、删除列、移动列组成顺序节点。
   - 上一步输出可直接作为下一步输入。
   - 支持预览到当前节点、预览完整计划、输出到主界面、保存/覆盖SQLite表、导出xlsx。
10. 新增文件工作流节点：获取文件列表、批量重命名，可与数据提取/替换/合并列组合生成新文件名。
11. 新增表格编辑类工作流节点：复制列、复制行、删除行、填充值、序列填充、区域填充。
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import sqlite3
import csv
import io
import re
import os
import sys
import json
import traceback
import copy
import queue
import time
import uuid
from datetime import datetime

from core.data_utils import (
    make_unique_headers_for_append as core_make_unique_headers_for_append,
    normalize_rows as core_normalize_rows,
    safe_cell as core_safe_cell,
)
from core.text_utils import (
    make_sql_columns as core_make_sql_columns,
    quote_ident as core_quote_ident,
    sanitize_sql_name as core_sanitize_sql_name,
)
from db import PluginDatabaseAPI, TableAccessManager
from plugin_runtime.scanner import scan_plugins
from shared.atomic_json_utils import atomic_write_json, load_json_with_backup
from workflow.nodes.data_nodes import (
    apply_unmatched_format_value as workflow_apply_unmatched_format_value,
    apply_unmatched_extract as workflow_apply_unmatched_extract,
    add_plan_filter_required_field as workflow_add_plan_filter_required_field,
    build_plan_filter_right_index as workflow_build_plan_filter_right_index,
    build_date_parts as workflow_build_date_parts,
    build_format_component_columns as workflow_build_format_component_columns,
    build_time_parts as workflow_build_time_parts,
    complete_format_year as workflow_complete_format_year,
    collect_plan_filter_required_fields as workflow_collect_plan_filter_required_fields,
    ensure_column_count as workflow_ensure_column_count,
    ensure_field_exists as workflow_ensure_field_exists,
    ensure_row_count as workflow_ensure_row_count,
    ensure_target_cell_limit as workflow_ensure_target_cell_limit,
    eval_plan_condition_record as workflow_eval_plan_condition_record,
    eval_plan_join_rule_record as workflow_eval_plan_join_rule_record,
    extract_one_value as workflow_extract_one_value,
    format_output_value as workflow_format_output_value,
    format_numeric_column_result as workflow_format_numeric_column_result,
    format_sequence_value as workflow_format_sequence_value,
    get_plan_filter_config_warnings as workflow_get_plan_filter_config_warnings,
    get_plan_filter_field_owner as workflow_get_plan_filter_field_owner,
    get_plan_filter_hash_join_availability as workflow_get_plan_filter_hash_join_availability,
    get_plan_filter_hash_join_rules as workflow_get_plan_filter_hash_join_rules,
    get_plan_filter_output_base_headers as workflow_get_plan_filter_output_base_headers,
    get_plan_filter_output_header_conflicts as workflow_get_plan_filter_output_header_conflicts,
    get_plan_filter_output_headers as workflow_get_plan_filter_output_headers,
    get_required_columns_for_plan_table as workflow_get_required_columns_for_plan_table,
    get_datetime_parse_warning as workflow_get_datetime_parse_warning,
    get_config_cell_value as workflow_get_config_cell_value,
    get_cycle_source_values_by_config as workflow_get_cycle_source_values_by_config,
    get_fill_targets as workflow_get_fill_targets,
    get_source_area_values_by_config as workflow_get_source_area_values_by_config,
    get_source_column_values_by_config as workflow_get_source_column_values_by_config,
    get_source_row_multi_field_values_by_config as workflow_get_source_row_multi_field_values_by_config,
    get_numeric_node_row_indexes as workflow_get_numeric_node_row_indexes,
    get_row_mapping_end_index as workflow_get_row_mapping_end_index,
    iter_plan_filter_join_candidates as workflow_iter_plan_filter_join_candidates,
    last_non_empty_row_index_by_field as workflow_last_non_empty_row_index_by_field,
    make_current_table_records as workflow_make_current_table_records,
    make_unique_plan_headers as workflow_make_unique_plan_headers,
    match_value_output_column_match as workflow_match_value_output_column_match,
    normalize_datetime_source_text as workflow_normalize_datetime_source_text,
    normalize_filter_condition_value_source as workflow_normalize_filter_condition_value_source,
    normalize_plan_filter_config_field_references as workflow_normalize_plan_filter_config_field_references,
    normalize_plan_filter_field_reference as workflow_normalize_plan_filter_field_reference,
    numeric_node_fallback_value as workflow_numeric_node_fallback_value,
    plan_filter_condition_dependencies as workflow_plan_filter_condition_dependencies,
    plan_filter_field_belongs_to_table as workflow_plan_filter_field_belongs_to_table,
    parse_new_columns_specs as workflow_parse_new_columns_specs,
    parse_numeric_value_for_column_op as workflow_parse_numeric_value_for_column_op,
    parse_date_auto_common as workflow_parse_date_auto_common,
    parse_date_delimited as workflow_parse_date_delimited,
    parse_date_fixed as workflow_parse_date_fixed,
    parse_format_datetime_value as workflow_parse_format_datetime_value,
    parse_format_int as workflow_parse_format_int,
    parse_int as workflow_parse_int,
    parse_time_auto_common as workflow_parse_time_auto_common,
    parse_time_delimited as workflow_parse_time_delimited,
    parse_time_fixed as workflow_parse_time_fixed,
    post_extract_result as workflow_post_extract_result,
    render_current_datetime_template as workflow_render_current_datetime_template,
    render_format_template as workflow_render_format_template,
    record_passes_plan_conditions as workflow_record_passes_plan_conditions,
    record_passes_plan_join_rules as workflow_record_passes_plan_join_rules,
    record_survives_available_plan_conditions as workflow_record_survives_available_plan_conditions,
    resolve_plan_condition_value as workflow_resolve_plan_condition_value,
    resolve_area_end_row_index as workflow_resolve_area_end_row_index,
    resolve_sequence_count_by_source as workflow_resolve_sequence_count_by_source,
    resolve_start_row_index_by_mode as workflow_resolve_start_row_index_by_mode,
    row_is_empty as workflow_row_is_empty,
    should_write_cell as workflow_should_write_cell,
    slice_by_position as workflow_slice_by_position,
    split_by_config_delimiter as workflow_split_by_config_delimiter,
)
from workflow.nodes.file_nodes import (
    is_hidden_path as workflow_is_hidden_path,
    parse_extensions_filter as workflow_parse_extensions_filter,
)
from workflow.nodes.group_nodes import (
    build_group_input_table as workflow_build_group_input_table,
    make_group_child_context as workflow_make_group_child_context,
    normalize_group_sqlite_mode as workflow_normalize_group_sqlite_mode,
    normalize_group_transit_conflict_mode as workflow_normalize_group_transit_conflict_mode,
    parse_group_input_fields as workflow_parse_group_input_fields,
)
from workflow.nodes.loop_nodes import (
    evaluate_loop_condition as workflow_evaluate_loop_condition,
    find_loop_judge_index as workflow_find_loop_judge_index,
    find_loop_start_index as workflow_find_loop_start_index,
    loop_last_non_empty_row_index as workflow_loop_last_non_empty_row_index,
)
from workflow.default_configs import default_config_for_type as workflow_default_config_for_type
from workflow.advanced_filter_window_logic import (
    add_advanced_filter_condition as workflow_add_advanced_filter_condition,
    add_advanced_filter_join_rule as workflow_add_advanced_filter_join_rule,
    add_advanced_filter_output_fields as workflow_add_advanced_filter_output_fields,
    add_all_advanced_filter_output_fields as workflow_add_all_advanced_filter_output_fields,
    build_advanced_filter_field_display_cache as workflow_build_advanced_filter_field_display_cache,
    build_advanced_filter_preview_rows as workflow_build_advanced_filter_preview_rows,
    build_advanced_filter_template_data as workflow_build_advanced_filter_template_data,
    build_advanced_filter_result_records as workflow_build_advanced_filter_result_records,
    clear_advanced_filter_items as workflow_clear_advanced_filter_items,
    dedupe_advanced_filter_preview_rows as workflow_dedupe_advanced_filter_preview_rows,
    eval_advanced_filter_condition as workflow_eval_advanced_filter_condition,
    eval_advanced_filter_conditions as workflow_eval_advanced_filter_conditions,
    eval_advanced_filter_join_rule as workflow_eval_advanced_filter_join_rule,
    eval_advanced_filter_join_rules as workflow_eval_advanced_filter_join_rules,
    filter_advanced_filter_valid_state as workflow_filter_advanced_filter_valid_state,
    format_advanced_filter_db_value as workflow_format_advanced_filter_db_value,
    get_advanced_filter_output_fields as workflow_get_advanced_filter_output_fields,
    load_advanced_filter_table_records as workflow_load_advanced_filter_table_records,
    normalize_advanced_filter_template_data as workflow_normalize_advanced_filter_template_data,
    parse_advanced_filter_number as workflow_parse_advanced_filter_number,
    parse_positive_int_setting as workflow_parse_positive_int_setting,
    remove_advanced_filter_items_by_indexes as workflow_remove_advanced_filter_items_by_indexes,
    remove_advanced_filter_output_fields as workflow_remove_advanced_filter_output_fields,
    select_advanced_filter_combo_defaults as workflow_select_advanced_filter_combo_defaults,
    select_advanced_filter_template_tables as workflow_select_advanced_filter_template_tables,
)
from workflow.filter_config_window_mixin import FilterConfigWindowMixin
from workflow.group_config_window_mixin import GroupConfigWindowMixin
from workflow.plan_preview_mixin import PlanPreviewMixin
from workflow.plan_workflow_window_mixin import PlanWorkflowUiMixin
from workflow.plugin_config_window_mixin import PluginConfigWindowMixin
from workflow.table_access_window_mixin import TableAccessWindowMixin
from workflow.workflow_execution_mixin import WorkflowExecutionMixin
from workflow.workflow_node_execution_mixin import WorkflowNodeExecutionMixin
from workflow import group_field_analysis as workflow_group_field_analysis
from workflow import group_template_ui as workflow_group_template_ui
from workflow.nodes.transit_nodes import (
    append_headers_rows as workflow_append_headers_rows,
    make_unique_transit_name as workflow_make_unique_transit_name,
)
from workflow.nodes.writeback_nodes import (
    build_writeback_full_structure_rows_for_sqlite as workflow_build_writeback_full_structure_rows_for_sqlite,
    compare_writeback_values as workflow_compare_writeback_values,
)
from workflow.workflow_config_builder_mixin import WorkflowConfigBuilderMixin
from workflow.workflow_control_runtime_mixin import WorkflowControlRuntimeMixin
from workflow.workflow_jump_mixin import WorkflowJumpMixin
from workflow.workflow_output_runtime_mixin import WorkflowOutputRuntimeMixin
from workflow.workflow_plugin_runtime_mixin import WorkflowPluginRuntimeMixin
from workflow.workflow_table_runtime_mixin import WorkflowTableRuntimeMixin
from workflow.table_access_precheck import (
    find_table_access_field_rule as workflow_find_table_access_field_rule,
    find_matching_table_access_entry as workflow_find_matching_table_access_entry,
    make_table_access_precheck_issue as workflow_make_table_access_precheck_issue,
    normalize_precheck_transit_name as workflow_normalize_precheck_transit_name,
    table_access_entry_match_score as workflow_table_access_entry_match_score,
    table_access_field_items as workflow_table_access_field_items,
    table_access_entry_status as workflow_table_access_entry_status,
    table_access_entry_table_label as workflow_table_access_entry_table_label,
    table_access_operation_summary as workflow_table_access_operation_summary,
    table_access_precheck_actionable as workflow_table_access_precheck_actionable,
    table_access_precheck_blocking as workflow_table_access_precheck_blocking,
    table_access_precheck_summary_text as workflow_table_access_precheck_summary_text,
)
from workflow.table_access_defaults import (
    build_default_table_access_for_node as workflow_build_default_table_access_for_node,
)
from workflow.table_access_window_ui import (
    apply_auto_field_mapping_by_name as workflow_apply_auto_field_mapping_by_name,
    apply_auto_field_mapping_by_order as workflow_apply_auto_field_mapping_by_order,
    clear_field_mapping as workflow_clear_field_mapping,
    delete_table_access_entry as workflow_delete_table_access_entry,
    delete_field_mapping_entry as workflow_delete_field_mapping_entry,
    field_mapping_item as workflow_field_mapping_item,
    field_mapping_mode_display as workflow_field_mapping_mode_display,
    field_mapping_mode_value as workflow_field_mapping_mode_value,
    load_field_form as workflow_load_field_form,
    make_table_access_field_key as workflow_make_table_access_field_key,
    rebuild_table_access as workflow_rebuild_table_access,
    render_field_mapping_tree as workflow_render_field_mapping_tree,
    render_table_access_tree as workflow_render_table_access_tree,
    reset_field_form as workflow_reset_field_form,
    save_table_access_entry as workflow_save_table_access_entry,
    selected_field_key as workflow_selected_field_key,
    table_access_preset_config as workflow_table_access_preset_config,
    upsert_field_mapping_entry as workflow_upsert_field_mapping_entry,
)


def get_app_dir():
    """
    返回程序真实工作目录。

    - 直接运行 .py：使用 .py 文件所在目录。
    - PyInstaller 打包为 exe 后：使用 exe 所在目录。

    这样 plan / logs / export / 默认数据库等目录不会被创建到
    PyInstaller 单文件模式的 C 盘临时解压目录 _MEIxxxxx 中。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def load_json_file_with_recovery(path, parent=None):
    data, info = load_json_with_backup(path)
    warning = info.get("warning", "")
    if warning:
        messagebox.showwarning("配置已从备份恢复", warning, parent=parent)
    return data





class ClipboardTableApp:
    def __init__(self, root):
        self.root = root
        self.root.title("剪贴板表格解析器 - SQLite保存版")
        self.root.geometry("1420x760")

        self.raw_data = ""
        self.headers = []
        self.rows = []

        self.edit_mode = False
        self.edit_entry = None

        # 主界面搜索状态
        self.search_var = tk.StringVar(value="")
        self.search_matches = []
        self.search_index = -1

        # 程序真实目录：兼容直接运行 .py 和 PyInstaller 单文件 exe。
        # 所有需要长期保留的文件都应基于此目录，避免写到 _MEI 临时目录。
        self.app_dir = get_app_dir()

        self.db_path_var = tk.StringVar(value=os.path.join(self.app_dir, "clipboard_tables.db"))
        self.table_name_var = tk.StringVar(value="paste_table")
        self.first_row_header_var = tk.BooleanVar(value=True)
        self.recreate_table_var = tk.BooleanVar(value=True)
        self.edit_btn_text = tk.StringVar(value="修改模式:关")

        self.build_ui()

    def build_ui(self):
        top_frame = ttk.Frame(self.root, padding=8)
        top_frame.pack(fill=tk.X)

        ttk.Button(
            top_frame,
            text="读取剪贴板并解析",
            command=self.load_clipboard
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="清空预览",
            command=self.clear_preview
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="删除字段名，并用下一行作为字段名",
            command=self.delete_header_and_promote_next_row
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            textvariable=self.edit_btn_text,
            command=self.toggle_edit_mode
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="计划 / 工作流处理",
            command=self.open_plan_workflow
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="批量替换 / 数据处理",
            command=self.open_batch_replace
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="数据提取 / 字段生成",
            command=self.open_data_extract
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="合并列 / 生成新列",
            command=self.open_merge_columns
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="高级筛选 / 数据匹配",
            command=self.open_advanced_filter
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="导出为 xlsx",
            command=self.export_current_preview_to_xlsx
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="保存到 SQLite",
            command=self.save_to_sqlite
        ).pack(side=tk.LEFT, padx=4)

        ttk.Button(
            top_frame,
            text="删除当前表",
            command=self.delete_current_sqlite_table
        ).pack(side=tk.LEFT, padx=4)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)

        # 主界面选项区拆成独立行，避免不同 row 共用同一个 grid 列宽互相影响。
        # 之前搜索按钮通过较大的 padx 放在 option_frame 的 column=1，
        # 会把数据库路径输入框所在列撑宽，导致“选择 / 刷新表名”整体右移。
        option_frame = ttk.Frame(self.root, padding=8)
        option_frame.pack(fill=tk.X)

        # 第1行：数据库路径设置
        db_frame = ttk.Frame(option_frame)
        db_frame.pack(fill=tk.X, anchor=tk.W)

        ttk.Label(db_frame, text="数据库：").pack(side=tk.LEFT, padx=(4, 4))

        ttk.Entry(
            db_frame,
            textvariable=self.db_path_var,
            width=80
        ).pack(side=tk.LEFT, padx=(4, 4))

        ttk.Button(
            db_frame,
            text="选择",
            command=self.choose_db
        ).pack(side=tk.LEFT, padx=(4, 4))

        ttk.Button(
            db_frame,
            text="刷新表名",
            command=self.refresh_table_list
        ).pack(side=tk.LEFT, padx=(4, 4))

        # 第2行：表名与保存选项
        table_option_frame = ttk.Frame(option_frame)
        table_option_frame.pack(fill=tk.X, anchor=tk.W, pady=(6, 0))

        ttk.Label(table_option_frame, text="表名：").pack(side=tk.LEFT, padx=(4, 4))

        self.table_combo = ttk.Combobox(
            table_option_frame,
            textvariable=self.table_name_var,
            width=32,
            state="normal"
        )
        self.table_combo.pack(side=tk.LEFT, padx=(4, 18))

        self.table_combo.configure(postcommand=self.refresh_table_list)
        self.table_combo.bind("<<ComboboxSelected>>", self.on_table_selected)

        ttk.Checkbutton(
            table_option_frame,
            text="第一行作为字段名",
            variable=self.first_row_header_var,
            command=self.reparse_current_raw
        ).pack(side=tk.LEFT, padx=(12, 12))

        ttk.Checkbutton(
            table_option_frame,
            text="保存时重建同名表",
            variable=self.recreate_table_var
        ).pack(side=tk.LEFT, padx=(12, 12))

        # 第3行：搜索区。搜索按钮保留你指定的 padx=330，但只影响 search_frame 自身，
        # 不再影响上方数据库行和表名行的布局。
        search_frame = ttk.Frame(option_frame)
        search_frame.pack(fill=tk.X, anchor=tk.W, pady=(6, 0))

        ttk.Label(search_frame, text="搜索：").grid(row=0, column=0, sticky=tk.W, padx=(4, 4), pady=4)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=38)
        search_entry.grid(row=0, column=1, sticky=tk.W, padx=(4, 4), pady=4)
        search_entry.bind("<Return>", lambda e: self.search_main_preview(reset=True))
        ttk.Button(search_frame, text="搜索", command=lambda: self.search_main_preview(reset=True)).grid(row=0, column=2, sticky=tk.W, padx=(12, 8), pady=4)
        ttk.Button(search_frame, text="上一个", command=self.search_main_prev).grid(row=0, column=3, sticky=tk.W, padx=(12, 8), pady=4)
        ttk.Button(search_frame, text="下一个", command=self.search_main_next).grid(row=0, column=4, sticky=tk.W, padx=(12, 8), pady=4)

        self.info_var = tk.StringVar(value="等待读取剪贴板数据。")
        ttk.Label(self.root, textvariable=self.info_var, padding=8).pack(fill=tk.X)

        table_frame = ttk.Frame(self.root)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.tree = ttk.Treeview(table_frame, show="headings")

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)

        self.tree.configure(
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set
        )

        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self.on_tree_double_click)

        # 程序启动时尝试刷新表名
        self.refresh_table_list()

    def open_plan_workflow(self):
        if not self.headers:
            messagebox.showwarning("提示", "当前没有可处理的数据，请先读取剪贴板或加载数据库表。")
            return

        PlanWorkflowWindow(self)

    def open_advanced_filter(self):
        db_path = self.db_path_var.get().strip()
        if not db_path:
            messagebox.showwarning("提示", "请先设置 SQLite 数据库路径。")
            return

        if not os.path.exists(db_path):
            messagebox.showwarning("提示", "当前 SQLite 数据库不存在，请先保存数据或选择已有数据库。")
            return

        AdvancedFilterWindow(self)


    def open_batch_replace(self):
        if not self.headers:
            messagebox.showwarning("提示", "当前没有可处理的数据，请先读取剪贴板或加载数据库表。")
            return

        BatchReplaceWindow(self)

    def open_data_extract(self):
        if not self.headers:
            messagebox.showwarning("提示", "当前没有可处理的数据，请先读取剪贴板或加载数据库表。")
            return

        DataExtractWindow(self)

    def open_merge_columns(self):
        if not self.headers:
            messagebox.showwarning("提示", "当前没有可处理的数据，请先读取剪贴板或加载数据库表。")
            return

        MergeColumnsWindow(self)

    def normalize_sheet_title(self, name):
        name = str(name or "导出数据").strip() or "导出数据"
        name = re.sub(r"[\\/*?:\[\]]", "_", name)
        return name[:31] or "导出数据"

    def column_letter(self, index):
        result = ""
        while index > 0:
            index, rem = divmod(index - 1, 26)
            result = chr(65 + rem) + result
        return result or "A"

    def calc_display_width(self, value):
        text = str(value or "")
        width = 0
        for ch in text:
            width += 2 if ord(ch) > 127 else 1
        return width

    def export_current_preview_to_xlsx(self, headers=None, rows=None, table_name=None, title="导出为 xlsx"):
        headers = list(self.headers if headers is None else headers)
        rows = [list(row) for row in (self.rows if rows is None else rows)]
        table_name = self.table_name_var.get() if table_name is None else table_name

        if not headers:
            messagebox.showwarning("提示", "当前没有可导出的表格字段。")
            return

        default_base = self.sanitize_sql_name(table_name, "导出数据")
        default_name = f"{default_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        path = filedialog.asksaveasfilename(
            title=title,
            defaultextension=".xlsx",
            initialfile=default_name,
            filetypes=[("Excel 工作簿", "*.xlsx"), ("所有文件", "*.*")]
        )

        if not path:
            return

        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            try:
                self.export_xlsx_with_openpyxl(path, headers=headers, rows=rows, table_name=table_name)
                engine = "openpyxl"
            except ModuleNotFoundError:
                self.export_xlsx_minimal(path, headers=headers, rows=rows, table_name=table_name)
                engine = "内置简易导出器"

            self.info_var.set(f"导出成功：{path}")
            messagebox.showinfo(
                "导出成功",
                f"已导出当前预览数据。\n\n文件：{path}\n行数：{len(rows)}\n列数：{len(headers)}\n导出方式：{engine}"
            )
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def export_xlsx_with_openpyxl(self, path, headers=None, rows=None, table_name=None):
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

        headers = [str(h) for h in (self.headers if headers is None else headers)]
        rows = [list(row) for row in (self.rows if rows is None else rows)]
        table_name = self.table_name_var.get() if table_name is None else table_name

        wb = Workbook()
        ws = wb.active
        ws.title = self.normalize_sheet_title(table_name)

        ws.append(headers)

        for row in rows:
            fixed = list(row)
            if len(fixed) < len(headers):
                fixed += [""] * (len(headers) - len(fixed))
            if len(fixed) > len(headers):
                fixed = fixed[:len(headers)]
            ws.append(["" if value is None else str(value) for value in fixed])

        header_fill = PatternFill("solid", fgColor="D9EAF7")
        thin = Side(style="thin", color="CCCCCC")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border

        for row_cells in ws.iter_rows(min_row=2):
            for cell in row_cells:
                cell.alignment = Alignment(vertical="center")
                cell.border = border

        ws.freeze_panes = "A2"
        if headers:
            last_col = self.column_letter(len(headers))
            ws.auto_filter.ref = f"A1:{last_col}{max(len(rows) + 1, 1)}"

        for col_idx, header in enumerate(headers, start=1):
            max_width = self.calc_display_width(header)
            for row in rows[:3000]:
                if col_idx - 1 < len(row):
                    max_width = max(max_width, self.calc_display_width(row[col_idx - 1]))
            ws.column_dimensions[self.column_letter(col_idx)].width = min(max(max_width + 2, 10), 40)

        wb.save(path)

    def export_xlsx_minimal(self, path, headers=None, rows=None, table_name=None):
        import zipfile
        from xml.sax.saxutils import escape

        headers = [str(h) for h in (self.headers if headers is None else headers)]
        rows = [list(row) for row in (self.rows if rows is None else rows)]
        sheet_rows = [headers]
        for row in rows:
            fixed = list(row)
            if len(fixed) < len(headers):
                fixed += [""] * (len(headers) - len(fixed))
            if len(fixed) > len(headers):
                fixed = fixed[:len(headers)]
            sheet_rows.append(["" if value is None else str(value) for value in fixed])

        def cell_xml(row_idx, col_idx, value, style_id="0"):
            ref = f"{self.column_letter(col_idx)}{row_idx}"
            value = escape(str(value))
            return f'<c r="{ref}" t="inlineStr" s="{style_id}"><is><t>{value}</t></is></c>'

        col_xml = []
        for col_idx, header in enumerate(headers, start=1):
            max_width = self.calc_display_width(header)
            for row in rows[:3000]:
                if col_idx - 1 < len(row):
                    max_width = max(max_width, self.calc_display_width(row[col_idx - 1]))
            width = min(max(max_width + 2, 10), 40)
            col_xml.append(f'<col min="{col_idx}" max="{col_idx}" width="{width}" customWidth="1"/>')

        row_xml_list = []
        for r_idx, row in enumerate(sheet_rows, start=1):
            style_id = "1" if r_idx == 1 else "0"
            cells = "".join(cell_xml(r_idx, c_idx, value, style_id) for c_idx, value in enumerate(row, start=1))
            row_xml_list.append(f'<row r="{r_idx}">{cells}</row>')

        last_col = self.column_letter(len(headers) if headers else 1)
        last_row = max(len(sheet_rows), 1)
        auto_filter = f'<autoFilter ref="A1:{last_col}{last_row}"/>' if headers else ""

        sheet_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheetViews>
    <sheetView workbookViewId="0">
      <pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>
      <selection pane="bottomLeft"/>
    </sheetView>
  </sheetViews>
  <cols>{''.join(col_xml)}</cols>
  <sheetData>{''.join(row_xml_list)}</sheetData>
  {auto_filter}
</worksheet>'''

        styles_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFD9EAF7"/></patternFill></fill></fills>
  <borders count="2"><border/><border><left style="thin"><color rgb="FFCCCCCC"/></left><right style="thin"><color rgb="FFCCCCCC"/></right><top style="thin"><color rgb="FFCCCCCC"/></top><bottom style="thin"><color rgb="FFCCCCCC"/></bottom></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/><xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/></cellXfs>
</styleSheet>'''

        content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''

        rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''

        workbook_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="{escape(self.normalize_sheet_title(self.table_name_var.get()))}" sheetId="1" r:id="rId1"/></sheets>
</workbook>'''

        workbook_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''

        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        core_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>ClipboardTableTool</dc:creator><cp:lastModifiedBy>ClipboardTableTool</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>'''

        app_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>ClipboardTableTool</Application></Properties>'''

        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("_rels/.rels", rels)
            zf.writestr("xl/workbook.xml", workbook_xml)
            zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
            zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
            zf.writestr("xl/styles.xml", styles_xml)
            zf.writestr("docProps/core.xml", core_xml)
            zf.writestr("docProps/app.xml", app_xml)

    def choose_db(self):
        path = filedialog.asksaveasfilename(
            title="选择 SQLite 数据库",
            defaultextension=".db",
            filetypes=[
                ("SQLite 数据库", "*.db"),
                ("SQLite 数据库", "*.sqlite"),
                ("所有文件", "*.*")
            ]
        )
        if path:
            self.db_path_var.set(path)
            self.refresh_table_list()

    def get_db_path(self):
        return self.db_path_var.get().strip()

    def get_table_names(self):
        db_path = self.get_db_path()

        if not db_path or not os.path.exists(db_path):
            return []
        return TableAccessManager(db_path, node_type="主界面").list_tables()

    def get_table_columns(self, table_name):
        db_path = self.get_db_path()

        return TableAccessManager(db_path, node_type="主界面").get_columns(table_name)

    def refresh_table_list(self):
        try:
            tables = self.get_table_names()
            self.table_combo["values"] = tables

            if tables:
                self.info_var.set(f"已读取当前数据库表：{len(tables)} 个。")
            else:
                self.info_var.set("当前数据库中没有普通数据表。")
        except Exception as e:
            self.table_combo["values"] = []
            self.info_var.set(f"读取数据库表失败：{e}")

    def on_table_selected(self, event=None):
        table_name = self.table_name_var.get().strip()

        if not table_name:
            return

        self.load_table_from_sqlite(table_name)

    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode

        if self.edit_mode:
            self.edit_btn_text.set("修改模式:开")
            self.info_var.set("修改模式已开启：双击预览表格中的单元格即可修改。")
        else:
            self.edit_btn_text.set("修改模式:关")
            self.info_var.set("修改模式已关闭。")

            if self.edit_entry is not None:
                self.edit_entry.destroy()
                self.edit_entry = None

    def on_tree_double_click(self, event):
        if not self.edit_mode:
            return

        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)

        if not row_id or not col_id:
            return

        try:
            col_index = int(col_id.replace("#", "")) - 1
            row_index = self.tree.index(row_id)
        except Exception:
            return

        if row_index < 0 or row_index >= len(self.rows):
            return

        if col_index < 0 or col_index >= len(self.headers):
            return

        bbox = self.tree.bbox(row_id, col_id)
        if not bbox:
            return

        x, y, width, height = bbox

        old_value = ""
        if col_index < len(self.rows[row_index]):
            old_value = self.rows[row_index][col_index]

        if self.edit_entry is not None:
            self.edit_entry.destroy()
            self.edit_entry = None

        entry = ttk.Entry(self.tree)
        entry.place(x=x, y=y, width=width, height=height)
        entry.insert(0, old_value)
        entry.select_range(0, tk.END)
        entry.focus()

        closed = {"done": False}

        def close_editor(save=True):
            if closed["done"]:
                return

            closed["done"] = True

            if save:
                new_value = entry.get()

                while len(self.rows[row_index]) < len(self.headers):
                    self.rows[row_index].append("")

                self.rows[row_index][col_index] = new_value

                values = list(self.tree.item(row_id, "values"))

                while len(values) < len(self.headers):
                    values.append("")

                values[col_index] = new_value
                self.tree.item(row_id, values=values)

                self.info_var.set(f"已修改：第 {row_index + 1} 行，第 {col_index + 1} 列。")

            entry.destroy()
            self.edit_entry = None

        entry.bind("<Return>", lambda e: close_editor(save=True))
        entry.bind("<FocusOut>", lambda e: close_editor(save=True))
        entry.bind("<Escape>", lambda e: close_editor(save=False))

        self.edit_entry = entry

    def load_clipboard(self):
        try:
            data = self.root.clipboard_get()
        except tk.TclError:
            messagebox.showwarning("提示", "剪贴板中没有可读取的文本数据。")
            return

        if not data.strip():
            messagebox.showwarning("提示", "剪贴板内容为空。")
            return

        self.raw_data = data
        self.parse_data(data)

    def reparse_current_raw(self):
        if self.raw_data:
            self.parse_data(self.raw_data)

    def parse_data(self, data):
        data = data.replace("\r\n", "\n").replace("\r", "\n")

        delimiter = "\t"
        if "\t" not in data and "," in data:
            delimiter = ","

        reader = csv.reader(io.StringIO(data), delimiter=delimiter)
        parsed_rows = []

        for row in reader:
            if not row:
                continue

            cleaned_row = [cell.strip() for cell in row]

            if all(cell == "" for cell in cleaned_row):
                continue

            parsed_rows.append(cleaned_row)

        if not parsed_rows:
            messagebox.showwarning("提示", "没有解析到有效表格数据。")
            return

        max_cols = max(len(row) for row in parsed_rows)

        normalized_rows = []
        for row in parsed_rows:
            row = row + [""] * (max_cols - len(row))
            normalized_rows.append(row)

        if self.first_row_header_var.get() and len(normalized_rows) >= 2:
            raw_headers = normalized_rows[0]
            data_rows = normalized_rows[1:]
        else:
            raw_headers = [f"列{i + 1}" for i in range(max_cols)]
            data_rows = normalized_rows

        self.headers = self.make_display_headers(raw_headers)
        self.rows = data_rows

        self.refresh_tree()

        self.info_var.set(
            f"解析完成：{len(self.rows)} 行 × {len(self.headers)} 列。"
            f" 分隔符：{'TAB制表符' if delimiter == chr(9) else '逗号'}"
        )

    def make_display_headers(self, headers):
        result = []
        used = {}

        for index, header in enumerate(headers, start=1):
            name = str(header).strip()
            if not name:
                name = f"列{index}"

            if name in used:
                used[name] += 1
                name = f"{name}_{used[name]}"
            else:
                used[name] = 1

            result.append(name)

        return result

    def refresh_tree(self):
        self.search_matches = []
        self.search_index = -1
        self.tree.delete(*self.tree.get_children())

        self.tree["columns"] = self.headers

        for col in self.headers:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=140, minwidth=80, anchor=tk.W, stretch=False)

        self.tree.tag_configure("search_match", background="#fff7cc")
        self.tree.tag_configure("search_current", background="#ffd580")

        for row in self.rows:
            fixed = list(row)
            if len(fixed) < len(self.headers):
                fixed += [""] * (len(self.headers) - len(fixed))
            if len(fixed) > len(self.headers):
                fixed = fixed[:len(self.headers)]
            self.tree.insert("", tk.END, values=fixed)

    def clear_main_search_marks(self):
        for iid in self.tree.get_children():
            self.tree.item(iid, tags=())
        self.search_matches = []
        self.search_index = -1

    def search_main_preview(self, reset=True):
        keyword = self.search_var.get().strip()
        if not keyword:
            messagebox.showwarning("提示", "请输入搜索关键词。")
            return

        keyword_lower = keyword.lower()
        self.clear_main_search_marks()

        for iid in self.tree.get_children():
            values = self.tree.item(iid, "values")
            row_text = "\t".join(str(v) for v in values)
            if keyword_lower in row_text.lower():
                self.search_matches.append(iid)
                self.tree.item(iid, tags=("search_match",))

        if not self.search_matches:
            self.info_var.set(f"搜索完成：未找到包含『{keyword}』的行。")
            return

        self.search_index = 0 if reset else max(self.search_index, 0)
        self.goto_main_search_result()
        self.info_var.set(f"搜索完成：找到 {len(self.search_matches)} 行匹配『{keyword}』。")

    def goto_main_search_result(self):
        if not self.search_matches:
            return
        self.search_index %= len(self.search_matches)
        current_iid = self.search_matches[self.search_index]
        for iid in self.search_matches:
            self.tree.item(iid, tags=("search_match",))
        self.tree.item(current_iid, tags=("search_current",))
        self.tree.selection_set(current_iid)
        self.tree.focus(current_iid)
        self.tree.see(current_iid)
        self.info_var.set(f"当前搜索结果：{self.search_index + 1}/{len(self.search_matches)}")

    def search_main_next(self):
        if not self.search_matches:
            self.search_main_preview(reset=True)
            return
        self.search_index += 1
        self.goto_main_search_result()

    def search_main_prev(self):
        if not self.search_matches:
            self.search_main_preview(reset=True)
            return
        self.search_index -= 1
        self.goto_main_search_result()

    def clear_preview(self):
        self.raw_data = ""
        self.headers = []
        self.rows = []

        if self.edit_entry is not None:
            self.edit_entry.destroy()
            self.edit_entry = None

        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = []
        self.info_var.set("已清空预览。")

    def delete_header_and_promote_next_row(self):
        if not self.headers:
            messagebox.showwarning("提示", "当前没有字段名，请先读取剪贴板数据。")
            return

        if not self.rows:
            messagebox.showwarning("提示", "当前没有下一行数据，无法提升为字段名。")
            return

        new_headers_raw = self.rows[0]
        new_rows = self.rows[1:]

        self.headers = self.make_display_headers(new_headers_raw)
        self.rows = new_rows

        self.refresh_tree()

        self.info_var.set(
            f"已删除原字段名，并使用下一行作为新字段名："
            f"{len(self.rows)} 行 × {len(self.headers)} 列。"
        )

    def sanitize_sql_name(self, name, default_name):
        return core_sanitize_sql_name(name, default_name)

    def make_sql_columns(self, headers):
        return core_make_sql_columns(headers)

    def quote_ident(self, name):
        return core_quote_ident(name)

    def table_exists(self, conn, table_name):
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return cur.fetchone() is not None

    def get_available_table_name(self, conn, base_name):
        if not self.table_exists(conn, base_name):
            return base_name

        suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_name = f"{base_name}_{suffix}"

        counter = 2
        while self.table_exists(conn, new_name):
            new_name = f"{base_name}_{suffix}_{counter}"
            counter += 1

        return new_name

    def format_db_value(self, value):
        if value is None:
            return ""

        if isinstance(value, bytes):
            return f"<BLOB {len(value)} bytes>"

        return str(value)

    def load_table_from_sqlite(self, table_name):
        db_path = self.db_path_var.get().strip()

        if not db_path:
            messagebox.showwarning("提示", "请先选择 SQLite 数据库。")
            return

        if not os.path.exists(db_path):
            messagebox.showwarning("提示", "当前数据库文件不存在。")
            return

        try:
            manager = TableAccessManager(db_path, node_type="主界面读取")
            if not manager.table_exists(table_name):
                messagebox.showwarning("提示", f"表不存在：{table_name}")
                return

            data = manager.read_table(table_name)
            headers = list(data.get("headers", []))

            if not headers:
                messagebox.showwarning("提示", f"表没有字段：{table_name}")
                return

            if self.edit_entry is not None:
                self.edit_entry.destroy()
                self.edit_entry = None

            self.raw_data = ""

            self.headers = self.make_display_headers(headers)
            self.rows = [list(row) for row in data.get("rows", [])]

            self.refresh_tree()

            self.info_var.set(
                f"已加载数据库表：{table_name}，"
                f"{len(self.rows)} 行 × {len(self.headers)} 列。"
            )

        except Exception as e:
            messagebox.showerror("读取表失败", str(e))

    def save_rows_to_sqlite_table(self, table_name_raw, headers, rows, recreate=True):
        db_path = self.get_db_path()
        if not db_path:
            raise ValueError("数据库路径为空。")

        table_name = self.sanitize_sql_name(table_name_raw, "result_table")
        sql_columns = self.make_sql_columns(headers)

        normalized_rows = []
        for row in rows:
            fixed_row = list(row)
            if len(fixed_row) < len(sql_columns):
                fixed_row += [""] * (len(sql_columns) - len(fixed_row))
            if len(fixed_row) > len(sql_columns):
                fixed_row = fixed_row[:len(sql_columns)]
            normalized_rows.append(fixed_row)

        mode = "replace" if recreate else "timestamp"
        info = TableAccessManager(db_path, node_type="主界面保存").write_table(
            table_name,
            sql_columns,
            normalized_rows,
            mode=mode,
        )
        self.refresh_table_list()

        return info.get("table_name", table_name), len(normalized_rows)

    def save_to_sqlite(self):
        if not self.headers or not self.rows:
            messagebox.showwarning("提示", "当前没有可保存的数据，请先读取剪贴板。")
            return

        db_path = self.db_path_var.get().strip()
        if not db_path:
            messagebox.showwarning("提示", "请填写 SQLite 数据库路径。")
            return

        table_name_raw = self.table_name_var.get().strip()

        try:
            table_name, row_count = self.save_rows_to_sqlite_table(
                table_name_raw=table_name_raw,
                headers=self.headers,
                rows=self.rows,
                recreate=self.recreate_table_var.get()
            )

            self.info_var.set(
                f"保存成功：数据库 {db_path}，表 {table_name}，共 {row_count} 行。"
            )

            messagebox.showinfo(
                "保存成功",
                f"已保存到 SQLite。\n\n数据库：{db_path}\n表名：{table_name}\n行数：{row_count}"
            )

        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def make_table_backup_name(self, conn, table_name):
        """生成当前 SQLite 表的备份表名，避免覆盖已有备份。"""
        base_name = f"{table_name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_name = base_name
        counter = 2
        while self.table_exists(conn, backup_name):
            backup_name = f"{base_name}_{counter}"
            counter += 1
        return backup_name

    def backup_sqlite_table_before_delete(self, conn, table_name):
        """删除前复制当前表到同库备份表，返回备份表名。"""
        backup_name = self.make_table_backup_name(conn, table_name)
        conn.execute(
            f"CREATE TABLE {self.quote_ident(backup_name)} AS "
            f"SELECT * FROM {self.quote_ident(table_name)}"
        )
        return backup_name

    def delete_current_sqlite_table(self):
        """主页删除当前下拉框选中的 SQLite 表。

        安全规则：
        1. 必须先开启修改模式。
        2. 只允许删除当前数据库中已存在、且当前下拉框选中的普通表。
        3. 删除前询问是否备份，备份失败则不删除。
        4. 删除前进行二次确认。
        """
        if not self.edit_mode:
            messagebox.showwarning(
                "禁止删除",
                "删除 SQLite 表属于高风险操作。\n\n请先开启“修改模式:开”，再点击“删除当前表”。"
            )
            return

        db_path = self.get_db_path()
        if not db_path:
            messagebox.showwarning("提示", "请先选择 SQLite 数据库。")
            return

        if not os.path.exists(db_path):
            messagebox.showwarning("提示", "当前 SQLite 数据库文件不存在。")
            return

        table_name = self.table_name_var.get().strip()
        if not table_name:
            messagebox.showwarning("提示", "请先在“表名”下拉框选择要删除的 SQLite 表。")
            return

        try:
            tables = self.get_table_names()
        except Exception as e:
            messagebox.showerror("读取表失败", str(e))
            return

        if table_name not in tables:
            messagebox.showwarning(
                "禁止删除",
                "只能删除当前 SQLite 数据库中已存在、并且从表名下拉框选中的普通表。\n\n"
                f"当前表名：{table_name}"
            )
            return

        if table_name.lower().startswith("sqlite_"):
            messagebox.showwarning("禁止删除", "不能删除 SQLite 系统内部表。")
            return

        backup_choice = messagebox.askyesnocancel(
            "删除当前表",
            "即将删除当前 SQLite 表：\n\n"
            f"数据库：{db_path}\n"
            f"表名：{table_name}\n\n"
            "是否先备份后删除？\n\n"
            "是：先复制为备份表，再删除当前表。\n"
            "否：不备份，直接删除当前表。\n"
            "取消：放弃删除。"
        )

        if backup_choice is None:
            self.info_var.set("已取消删除当前表。")
            return

        confirm_text = (
            "请再次确认删除操作。\n\n"
            f"将删除 SQLite 表：{table_name}\n"
        )
        if backup_choice:
            confirm_text += "删除前会先在当前数据库中创建备份表。\n\n"
        else:
            confirm_text += "本次选择不备份，删除后只能依靠你自己的数据库备份恢复。\n\n"
        confirm_text += "确认继续删除吗？"

        if not messagebox.askyesno("二次确认删除", confirm_text):
            self.info_var.set("已取消删除当前表。")
            return

        try:
            backup_name = TableAccessManager(db_path, node_type="主界面删除").drop_table(
                table_name,
                backup=bool(backup_choice),
            )

            self.refresh_table_list()

            if backup_name:
                self.table_name_var.set(backup_name)
                try:
                    self.load_table_from_sqlite(backup_name)
                except Exception:
                    self.clear_preview()
                msg = f"已备份并删除当前表。备份表：{backup_name}"
            else:
                self.table_name_var.set("")
                self.clear_preview()
                msg = f"已删除当前表：{table_name}"

            self.info_var.set(msg)
            messagebox.showinfo(
                "删除完成",
                f"已删除 SQLite 表：{table_name}"
                + (f"\n\n备份表：{backup_name}" if backup_name else "\n\n本次未创建备份表。")
            )

        except Exception as e:
            messagebox.showerror("删除失败", str(e))
            self.info_var.set(f"删除失败：{e}")



class DataExtractWindow:
    # 数据提取 / 字段生成窗口

    METHODS = [
        "正则提取",
        "固定位置提取",
        "从左取N位",
        "从右取N位",
        "按分隔符提取",
        "前后关键字之间提取",
        "指定字符前提取",
        "指定字符后提取",
        "删除前缀",
        "删除后缀",
    ]
    OUTPUT_MODES = ["生成新字段", "覆盖源字段"]
    UNMATCHED_MODES = ["留空", "保留原值", "填写固定值", "跳过该行"]
    POSITION_BASES = ["从1开始", "从0开始"]
    FIND_MODES = ["第一次出现", "最后一次出现"]

    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("数据提取 / 字段生成")
        self.window.geometry("1320x780")
        self.window.transient(app.root)

        self.preview_results = []
        self.last_backup = None

        self.source_field_var = tk.StringVar(value=app.headers[0] if app.headers else "")
        self.method_var = tk.StringVar(value="正则提取")
        self.output_mode_var = tk.StringVar(value="生成新字段")
        self.new_field_var = tk.StringVar(value="提取结果")
        self.unmatched_mode_var = tk.StringVar(value="留空")
        self.unmatched_fixed_var = tk.StringVar(value="未匹配")
        self.result_limit_var = tk.StringVar(value="1000")
        self.case_sensitive_var = tk.BooleanVar(value=True)
        self.strip_result_var = tk.BooleanVar(value=True)

        # 正则提取
        self.regex_pattern_var = tk.StringVar()
        self.regex_group_var = tk.StringVar(value="0")
        self.regex_find_all_var = tk.BooleanVar(value=False)
        self.regex_joiner_var = tk.StringVar(value=";")

        # 固定位置提取
        self.start_pos_var = tk.StringVar(value="1")
        self.extract_len_var = tk.StringVar(value="1")
        self.position_base_var = tk.StringVar(value="从1开始")

        # 左/右取N位
        self.n_chars_var = tk.StringVar(value="1")

        # 分隔符提取
        self.delimiter_var = tk.StringVar(value="-")
        self.part_index_var = tk.StringVar(value="1")
        self.ignore_empty_part_var = tk.BooleanVar(value=False)

        # 前后关键字之间提取
        self.before_key_var = tk.StringVar()
        self.after_key_var = tk.StringVar()
        self.between_occurrence_var = tk.StringVar(value="1")

        # 指定字符前/后提取
        self.marker_var = tk.StringVar(value="-")
        self.find_mode_var = tk.StringVar(value="第一次出现")

        # 删除前缀/后缀
        self.prefix_var = tk.StringVar()
        self.suffix_var = tk.StringVar()

        self.build_ui()
        self.update_param_ui()

    def build_ui(self):
        main = ttk.Frame(self.window, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        top = ttk.LabelFrame(main, text="1. 数据源与提取方式", padding=8)
        top.pack(fill=tk.X)

        ttk.Label(top, text="源字段：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
        self.source_combo = ttk.Combobox(top, textvariable=self.source_field_var, values=self.app.headers, width=28, state="readonly")
        self.source_combo.grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)

        ttk.Label(top, text="提取方式：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
        method_combo = ttk.Combobox(top, textvariable=self.method_var, values=self.METHODS, width=22, state="readonly")
        method_combo.grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)
        method_combo.bind("<<ComboboxSelected>>", lambda event: self.update_param_ui())

        ttk.Checkbutton(top, text="区分大小写", variable=self.case_sensitive_var).grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
        ttk.Checkbutton(top, text="提取结果去除首尾空格", variable=self.strip_result_var).grid(row=0, column=5, sticky=tk.W, padx=4, pady=4)

        self.param_frame = ttk.LabelFrame(main, text="2. 提取参数", padding=8)
        self.param_frame.pack(fill=tk.X, pady=8)

        output = ttk.LabelFrame(main, text="3. 输出设置", padding=8)
        output.pack(fill=tk.X)

        ttk.Label(output, text="输出方式：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
        output_combo = ttk.Combobox(output, textvariable=self.output_mode_var, values=self.OUTPUT_MODES, width=16, state="readonly")
        output_combo.grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
        output_combo.bind("<<ComboboxSelected>>", lambda event: self.update_output_state())

        ttk.Label(output, text="新字段名：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
        self.new_field_entry = ttk.Entry(output, textvariable=self.new_field_var, width=28)
        self.new_field_entry.grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)

        ttk.Label(output, text="未匹配时：").grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
        ttk.Combobox(output, textvariable=self.unmatched_mode_var, values=self.UNMATCHED_MODES, width=14, state="readonly").grid(row=0, column=5, sticky=tk.W, padx=4, pady=4)

        ttk.Label(output, text="固定值：").grid(row=0, column=6, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(output, textvariable=self.unmatched_fixed_var, width=18).grid(row=0, column=7, sticky=tk.W, padx=4, pady=4)

        center = ttk.LabelFrame(main, text="4. 提取结果预览", padding=6)
        center.pack(fill=tk.BOTH, expand=True, pady=8)

        self.preview_tree = ttk.Treeview(
            center,
            columns=("行号", "原内容", "提取结果", "状态"),
            show="headings",
            height=16
        )
        for col, width in [("行号", 70), ("原内容", 420), ("提取结果", 420), ("状态", 140)]:
            self.preview_tree.heading(col, text=col)
            self.preview_tree.column(col, width=width, anchor=tk.W, stretch=False)

        y_scroll = ttk.Scrollbar(center, orient=tk.VERTICAL, command=self.preview_tree.yview)
        x_scroll = ttk.Scrollbar(center, orient=tk.HORIZONTAL, command=self.preview_tree.xview)
        self.preview_tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.preview_tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        center.rowconfigure(0, weight=1)
        center.columnconfigure(0, weight=1)

        bottom = ttk.Frame(main)
        bottom.pack(fill=tk.X)

        ttk.Label(bottom, text="预览最大显示行数：").pack(side=tk.LEFT, padx=4)
        ttk.Entry(bottom, textvariable=self.result_limit_var, width=8).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="预览提取结果", command=self.preview_extract).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="执行提取", command=self.execute_extract).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="撤销上一次提取", command=self.undo_last_extract).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="保存当前结果为新表", command=self.save_current_result_to_new_table).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="保存规则模板", command=self.save_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="载入规则模板", command=self.load_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="关闭", command=self.window.destroy).pack(side=tk.RIGHT, padx=4)

        self.status_var = tk.StringVar(value="提示：正则提取直接使用 Python re 规则。分组 0 表示完整匹配，分组 1 表示第一个括号内容。")
        ttk.Label(main, textvariable=self.status_var, padding=(0, 6)).pack(fill=tk.X)
        self.update_output_state()

    def clear_param_frame(self):
        for child in self.param_frame.winfo_children():
            child.destroy()

    def update_param_ui(self):
        self.clear_param_frame()
        method = self.method_var.get()

        if method == "正则提取":
            ttk.Label(self.param_frame, text="Python正则：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.regex_pattern_var, width=60).grid(row=0, column=1, columnspan=4, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="提取分组：").grid(row=0, column=5, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.regex_group_var, width=8).grid(row=0, column=6, sticky=tk.W, padx=4, pady=4)
            ttk.Checkbutton(self.param_frame, text="提取全部匹配", variable=self.regex_find_all_var).grid(row=1, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="全部匹配连接符：").grid(row=1, column=2, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.regex_joiner_var, width=12).grid(row=1, column=3, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="示例：BP\\d+GK 或 客码[:：]([A-Za-z0-9_-]+)").grid(row=1, column=4, columnspan=4, sticky=tk.W, padx=4, pady=4)

        elif method == "固定位置提取":
            ttk.Label(self.param_frame, text="起始位置：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.start_pos_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="提取长度：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.extract_len_var, width=10).grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="位置规则：").grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
            ttk.Combobox(self.param_frame, textvariable=self.position_base_var, values=self.POSITION_BASES, width=12, state="readonly").grid(row=0, column=5, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="示例：123456789，起始3、长度4 → 3456（从1开始）").grid(row=1, column=0, columnspan=6, sticky=tk.W, padx=4, pady=4)

        elif method in ["从左取N位", "从右取N位"]:
            ttk.Label(self.param_frame, text="N：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.n_chars_var, width=10).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="示例：ABC123456，取3位 → 左取ABC / 右取456").grid(row=0, column=2, columnspan=5, sticky=tk.W, padx=4, pady=4)

        elif method == "按分隔符提取":
            ttk.Label(self.param_frame, text="分隔符：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.delimiter_var, width=16).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="取第几段：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.part_index_var, width=10).grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)
            ttk.Checkbutton(self.param_frame, text="忽略空段", variable=self.ignore_empty_part_var).grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="段序号从1开始；可填 -1 表示最后一段，-2 表示倒数第2段。").grid(row=1, column=0, columnspan=6, sticky=tk.W, padx=4, pady=4)

        elif method == "前后关键字之间提取":
            ttk.Label(self.param_frame, text="开始关键字：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.before_key_var, width=24).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="结束关键字：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.after_key_var, width=24).grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="第几个匹配：").grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.between_occurrence_var, width=8).grid(row=0, column=5, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="示例：型号[BP2526GK]，开始 型号[，结束 ] → BP2526GK").grid(row=1, column=0, columnspan=6, sticky=tk.W, padx=4, pady=4)

        elif method in ["指定字符前提取", "指定字符后提取"]:
            ttk.Label(self.param_frame, text="指定字符/字符串：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.marker_var, width=20).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="查找位置：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
            ttk.Combobox(self.param_frame, textvariable=self.find_mode_var, values=self.FIND_MODES, width=12, state="readonly").grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="示例：BP2526GK-35RD-01，指定 -，前提取 → BP2526GK").grid(row=1, column=0, columnspan=6, sticky=tk.W, padx=4, pady=4)

        elif method == "删除前缀":
            ttk.Label(self.param_frame, text="要删除的前缀：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.prefix_var, width=30).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="示例：HYBP2526GK 删除 HY → BP2526GK").grid(row=0, column=2, columnspan=5, sticky=tk.W, padx=4, pady=4)

        elif method == "删除后缀":
            ttk.Label(self.param_frame, text="要删除的后缀：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
            ttk.Entry(self.param_frame, textvariable=self.suffix_var, width=30).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
            ttk.Label(self.param_frame, text="示例：BP2526GK_TEMP 删除 _TEMP → BP2526GK").grid(row=0, column=2, columnspan=5, sticky=tk.W, padx=4, pady=4)

    def update_output_state(self):
        if self.output_mode_var.get() == "生成新字段":
            self.new_field_entry.configure(state="normal")
        else:
            self.new_field_entry.configure(state="disabled")

    def get_source_index(self):
        field = self.source_field_var.get().strip()
        if field not in self.app.headers:
            raise ValueError("请选择有效的源字段。")
        return self.app.headers.index(field)

    def parse_int(self, value, name):
        try:
            return int(str(value).strip())
        except Exception:
            raise ValueError(f"{name} 必须是整数。")

    def normalize_case(self, text):
        return text if self.case_sensitive_var.get() else text.lower()

    def find_marker_index(self, text, marker):
        if marker == "":
            raise ValueError("指定字符/字符串不能为空。")
        search_text = self.normalize_case(text)
        search_marker = self.normalize_case(marker)
        if self.find_mode_var.get() == "最后一次出现":
            return search_text.rfind(search_marker)
        return search_text.find(search_marker)

    def apply_unmatched(self, original, status):
        mode = self.unmatched_mode_var.get()
        if mode == "留空":
            return "", status
        if mode == "保留原值":
            return original, status
        if mode == "填写固定值":
            return self.unmatched_fixed_var.get(), status
        if mode == "跳过该行":
            return "", "跳过"
        return "", status

    def post_process_result(self, result):
        if result is None:
            result = ""
        result = str(result)
        if self.strip_result_var.get():
            result = result.strip()
        return result

    def extract_one(self, original):
        text = "" if original is None else str(original)
        method = self.method_var.get()

        try:
            if method == "正则提取":
                pattern = self.regex_pattern_var.get()
                if not pattern:
                    raise ValueError("正则表达式不能为空。")
                flags = 0 if self.case_sensitive_var.get() else re.IGNORECASE
                group_index = self.parse_int(self.regex_group_var.get(), "提取分组")

                if self.regex_find_all_var.get():
                    results = []
                    for m in re.finditer(pattern, text, flags):
                        try:
                            results.append(m.group(group_index))
                        except IndexError:
                            return self.apply_unmatched(text, "分组不存在")
                    if not results:
                        return self.apply_unmatched(text, "未匹配")
                    return self.post_process_result(self.regex_joiner_var.get().join(results)), "成功"

                m = re.search(pattern, text, flags)
                if not m:
                    return self.apply_unmatched(text, "未匹配")
                try:
                    return self.post_process_result(m.group(group_index)), "成功"
                except IndexError:
                    return self.apply_unmatched(text, "分组不存在")

            if method == "固定位置提取":
                start = self.parse_int(self.start_pos_var.get(), "起始位置")
                length = self.parse_int(self.extract_len_var.get(), "提取长度")
                if length < 0:
                    raise ValueError("提取长度不能小于0。")
                start_idx = start - 1 if self.position_base_var.get() == "从1开始" else start
                if start_idx < 0 or start_idx >= len(text):
                    return self.apply_unmatched(text, "越界")
                return self.post_process_result(text[start_idx:start_idx + length]), "成功"

            if method == "从左取N位":
                n = self.parse_int(self.n_chars_var.get(), "N")
                if n < 0:
                    raise ValueError("N不能小于0。")
                return self.post_process_result(text[:n]), "成功"

            if method == "从右取N位":
                n = self.parse_int(self.n_chars_var.get(), "N")
                if n < 0:
                    raise ValueError("N不能小于0。")
                return self.post_process_result(text[-n:] if n else ""), "成功"

            if method == "按分隔符提取":
                delimiter = self.delimiter_var.get()
                if delimiter == "":
                    raise ValueError("分隔符不能为空。")
                parts = text.split(delimiter)
                if self.ignore_empty_part_var.get():
                    parts = [p for p in parts if p != ""]
                part_index = self.parse_int(self.part_index_var.get(), "取第几段")
                if part_index == 0:
                    raise ValueError("段序号不能为0。正数从1开始，负数表示倒数。")
                idx = part_index - 1 if part_index > 0 else part_index
                if idx < -len(parts) or idx >= len(parts):
                    return self.apply_unmatched(text, "越界")
                return self.post_process_result(parts[idx]), "成功"

            if method == "前后关键字之间提取":
                start_key = self.before_key_var.get()
                end_key = self.after_key_var.get()
                if start_key == "" or end_key == "":
                    raise ValueError("开始关键字和结束关键字不能为空。")
                occurrence = self.parse_int(self.between_occurrence_var.get(), "第几个匹配")
                if occurrence <= 0:
                    raise ValueError("第几个匹配必须大于0。")

                search_text = self.normalize_case(text)
                search_start = self.normalize_case(start_key)
                search_end = self.normalize_case(end_key)
                pos = 0
                found = None
                for _ in range(occurrence):
                    s = search_text.find(search_start, pos)
                    if s < 0:
                        return self.apply_unmatched(text, "未匹配")
                    content_start = s + len(start_key)
                    e = search_text.find(search_end, content_start)
                    if e < 0:
                        return self.apply_unmatched(text, "未匹配")
                    found = text[content_start:e]
                    pos = e + len(end_key)
                return self.post_process_result(found), "成功"

            if method == "指定字符前提取":
                marker = self.marker_var.get()
                idx = self.find_marker_index(text, marker)
                if idx < 0:
                    return self.apply_unmatched(text, "未匹配")
                return self.post_process_result(text[:idx]), "成功"

            if method == "指定字符后提取":
                marker = self.marker_var.get()
                idx = self.find_marker_index(text, marker)
                if idx < 0:
                    return self.apply_unmatched(text, "未匹配")
                return self.post_process_result(text[idx + len(marker):]), "成功"

            if method == "删除前缀":
                prefix = self.prefix_var.get()
                if prefix == "":
                    raise ValueError("前缀不能为空。")
                if self.normalize_case(text).startswith(self.normalize_case(prefix)):
                    return self.post_process_result(text[len(prefix):]), "成功"
                return self.apply_unmatched(text, "未匹配")

            if method == "删除后缀":
                suffix = self.suffix_var.get()
                if suffix == "":
                    raise ValueError("后缀不能为空。")
                if self.normalize_case(text).endswith(self.normalize_case(suffix)):
                    return self.post_process_result(text[:-len(suffix)]), "成功"
                return self.apply_unmatched(text, "未匹配")

            raise ValueError(f"未知提取方式：{method}")

        except re.error as e:
            raise ValueError(f"正则错误：{e}")

    def build_preview_results(self):
        source_idx = self.get_source_index()
        results = []
        for row_index, row in enumerate(self.app.rows):
            original = ""
            if source_idx < len(row):
                original = row[source_idx]
            extracted, status = self.extract_one(original)
            results.append({
                "row_index": row_index,
                "original": "" if original is None else str(original),
                "extracted": "" if extracted is None else str(extracted),
                "status": status
            })
        return results

    def get_preview_limit(self):
        try:
            limit = int(self.result_limit_var.get().strip())
            return max(limit, 1)
        except Exception:
            return 1000

    def refresh_preview_tree(self, results):
        self.preview_tree.delete(*self.preview_tree.get_children())
        limit = self.get_preview_limit()
        for item in results[:limit]:
            self.preview_tree.insert("", tk.END, values=(
                item["row_index"] + 1,
                item["original"],
                item["extracted"],
                item["status"]
            ))

    def preview_extract(self):
        try:
            results = self.build_preview_results()
        except Exception as e:
            messagebox.showwarning("预览失败", str(e))
            return

        self.preview_results = results
        self.refresh_preview_tree(results)
        success_count = sum(1 for r in results if r.get("status") == "成功")
        skip_count = sum(1 for r in results if r.get("status") == "跳过")
        self.status_var.set(
            f"预览完成：共 {len(results)} 行，成功 {success_count} 行，跳过 {skip_count} 行，"
            f"当前显示前 {min(self.get_preview_limit(), len(results))} 行。"
        )

    def get_unique_header(self, base_name, headers):
        name = str(base_name or "提取结果").strip() or "提取结果"
        if name not in headers:
            return name
        counter = 2
        while f"{name}_{counter}" in headers:
            counter += 1
        return f"{name}_{counter}"

    def execute_extract(self):
        try:
            results = self.build_preview_results()
            source_idx = self.get_source_index()
        except Exception as e:
            messagebox.showwarning("执行失败", str(e))
            return

        if self.output_mode_var.get() == "覆盖源字段":
            ok = messagebox.askyesno("确认覆盖", "覆盖源字段会直接修改当前预览数据，是否继续？")
            if not ok:
                return

        self.last_backup = {
            "headers": list(self.app.headers),
            "rows": [list(row) for row in self.app.rows]
        }

        changed = 0
        skipped = 0
        if self.output_mode_var.get() == "生成新字段":
            new_field = self.get_unique_header(self.new_field_var.get(), self.app.headers)
            self.app.headers.append(new_field)
            for item, row in zip(results, self.app.rows):
                if item["status"] == "跳过":
                    skipped += 1
                    row.append("")
                    continue
                row.append(item["extracted"])
                changed += 1
        else:
            for item, row in zip(results, self.app.rows):
                if item["status"] == "跳过":
                    skipped += 1
                    continue
                while len(row) < len(self.app.headers):
                    row.append("")
                if source_idx < len(row):
                    row[source_idx] = item["extracted"]
                    changed += 1

        self.preview_results = results
        self.refresh_preview_tree(results)
        self.app.refresh_tree()
        self.app.info_var.set(f"数据提取完成：修改/写入 {changed} 行，跳过 {skipped} 行。")
        self.status_var.set(f"执行完成：修改/写入 {changed} 行，跳过 {skipped} 行。可点击“撤销上一次提取”恢复。")

    def undo_last_extract(self):
        if not self.last_backup:
            messagebox.showwarning("提示", "没有可撤销的提取操作。")
            return

        self.app.headers = list(self.last_backup["headers"])
        self.app.rows = [list(row) for row in self.last_backup["rows"]]
        self.last_backup = None
        self.source_combo.configure(values=self.app.headers)
        if self.app.headers:
            self.source_field_var.set(self.app.headers[0])
        self.app.refresh_tree()
        self.app.info_var.set("已撤销上一次数据提取。")
        self.status_var.set("已撤销上一次数据提取。")

    def save_current_result_to_new_table(self):
        if not self.app.headers:
            messagebox.showwarning("提示", "当前没有可保存的数据。")
            return
        default_name = f"提取结果_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        name = simpledialog.askstring("保存为新表", "请输入新表名：", initialvalue=default_name, parent=self.window)
        if not name:
            return
        try:
            table_name, row_count = self.app.save_rows_to_sqlite_table(
                table_name_raw=name,
                headers=self.app.headers,
                rows=self.app.rows,
                recreate=False
            )
            self.app.table_name_var.set(table_name)
            self.app.info_var.set(f"数据提取结果已保存为新表：{table_name}，共 {row_count} 行。")
            messagebox.showinfo("保存成功", f"已保存为新表：{table_name}\n行数：{row_count}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def collect_template(self):
        return {
            "source_field": self.source_field_var.get(),
            "method": self.method_var.get(),
            "output_mode": self.output_mode_var.get(),
            "new_field": self.new_field_var.get(),
            "unmatched_mode": self.unmatched_mode_var.get(),
            "unmatched_fixed": self.unmatched_fixed_var.get(),
            "case_sensitive": bool(self.case_sensitive_var.get()),
            "strip_result": bool(self.strip_result_var.get()),
            "regex_pattern": self.regex_pattern_var.get(),
            "regex_group": self.regex_group_var.get(),
            "regex_find_all": bool(self.regex_find_all_var.get()),
            "regex_joiner": self.regex_joiner_var.get(),
            "start_pos": self.start_pos_var.get(),
            "extract_len": self.extract_len_var.get(),
            "position_base": self.position_base_var.get(),
            "n_chars": self.n_chars_var.get(),
            "delimiter": self.delimiter_var.get(),
            "part_index": self.part_index_var.get(),
            "ignore_empty_part": bool(self.ignore_empty_part_var.get()),
            "before_key": self.before_key_var.get(),
            "after_key": self.after_key_var.get(),
            "between_occurrence": self.between_occurrence_var.get(),
            "marker": self.marker_var.get(),
            "find_mode": self.find_mode_var.get(),
            "prefix": self.prefix_var.get(),
            "suffix": self.suffix_var.get(),
        }

    def apply_template(self, data):
        def set_if(name, var):
            if name in data:
                var.set(data[name])

        set_if("source_field", self.source_field_var)
        set_if("method", self.method_var)
        set_if("output_mode", self.output_mode_var)
        set_if("new_field", self.new_field_var)
        set_if("unmatched_mode", self.unmatched_mode_var)
        set_if("unmatched_fixed", self.unmatched_fixed_var)
        if "case_sensitive" in data:
            self.case_sensitive_var.set(bool(data["case_sensitive"]))
        if "strip_result" in data:
            self.strip_result_var.set(bool(data["strip_result"]))
        set_if("regex_pattern", self.regex_pattern_var)
        set_if("regex_group", self.regex_group_var)
        if "regex_find_all" in data:
            self.regex_find_all_var.set(bool(data["regex_find_all"]))
        set_if("regex_joiner", self.regex_joiner_var)
        set_if("start_pos", self.start_pos_var)
        set_if("extract_len", self.extract_len_var)
        set_if("position_base", self.position_base_var)
        set_if("n_chars", self.n_chars_var)
        set_if("delimiter", self.delimiter_var)
        set_if("part_index", self.part_index_var)
        if "ignore_empty_part" in data:
            self.ignore_empty_part_var.set(bool(data["ignore_empty_part"]))
        set_if("before_key", self.before_key_var)
        set_if("after_key", self.after_key_var)
        set_if("between_occurrence", self.between_occurrence_var)
        set_if("marker", self.marker_var)
        set_if("find_mode", self.find_mode_var)
        set_if("prefix", self.prefix_var)
        set_if("suffix", self.suffix_var)
        self.update_param_ui()
        self.update_output_state()

    def save_template(self):
        path = filedialog.asksaveasfilename(
            title="保存数据提取规则模板",
            defaultextension=".json",
            filetypes=[("JSON 模板", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return
        try:
            atomic_write_json(path, self.collect_template())
            self.status_var.set(f"已保存模板：{path}")
        except Exception as e:
            messagebox.showerror("保存模板失败", str(e))

    def load_template(self):
        path = filedialog.askopenfilename(
            title="载入数据提取规则模板",
            filetypes=[("JSON 模板", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return
        try:
            data = load_json_file_with_recovery(path, parent=self.window)
            self.apply_template(data)
            self.status_var.set(f"已载入模板：{path}")
        except Exception as e:
            messagebox.showerror("载入模板失败", str(e))



class MergeColumnsWindow:
    """
    合并列 / 生成新列窗口。

    作用：
    - 从当前主界面预览数据中选择多个字段；
    - 通过“合并顺序列表”明确字段拼接顺序；
    - 支持每两列之间设置不同连接符，也支持自定义连接符；
    - 生成一个新的字段列；
    - 支持预览、执行、撤销、保存/载入模板。
    """

    SEPARATOR_OPTIONS = [
        "空字符", "空格", "换行", "Windows换行", "制表符",
        "-", "_", "/", "\\", "|", ",", ";", ":", ".", "+", "自定义"
    ]

    SEPARATOR_MAP = {
        "空字符": "",
        "空格": " ",
        "换行": "\n",
        "Windows换行": "\r\n",
        "制表符": "\t",
        "-": "-",
        "_": "_",
        "/": "/",
        "\\": "\\",
        "|": "|",
        ",": ",",
        ";": ";",
        ":": ":",
        ".": ".",
        "+": "+",
    }

    def __init__(self, app):
        self.app = app
        self.last_snapshot = None
        self.separator_rows = []

        self.window = tk.Toplevel(app.root)
        self.window.title("合并列 / 生成新列")
        self.window.geometry("1120x760")
        self.window.transient(app.root)

        self.new_field_var = tk.StringVar(value="合并结果")
        self.default_separator_var = tk.StringVar(value="空字符")
        self.default_separator_custom_var = tk.StringVar(value="")
        self.skip_empty_var = tk.BooleanVar(value=False)
        self.trim_value_var = tk.BooleanVar(value=False)
        self.empty_placeholder_var = tk.StringVar(value="")
        self.preview_limit_var = tk.IntVar(value=500)
        self.status_var = tk.StringVar(value="请从左侧字段池添加字段到右侧合并顺序列表。")

        self.build_ui()

    def build_ui(self):
        main = ttk.Frame(self.window, padding=10)
        main.pack(fill=tk.BOTH, expand=True)

        source_frame = ttk.LabelFrame(main, text="1. 字段选择与合并顺序", padding=8)
        source_frame.pack(fill=tk.X)

        # 左侧：全部字段池
        left = ttk.Frame(source_frame)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 8))

        ttk.Label(left, text="可选字段：").pack(anchor=tk.W)

        available_frame = ttk.Frame(left)
        available_frame.pack(fill=tk.Y, pady=4)

        self.available_listbox = tk.Listbox(
            available_frame,
            selectmode=tk.EXTENDED,
            height=12,
            width=32,
            exportselection=False
        )
        available_scroll = ttk.Scrollbar(available_frame, orient=tk.VERTICAL, command=self.available_listbox.yview)
        self.available_listbox.configure(yscrollcommand=available_scroll.set)
        self.available_listbox.pack(side=tk.LEFT, fill=tk.Y)
        available_scroll.pack(side=tk.LEFT, fill=tk.Y)

        self.refresh_available_fields()
        self.available_listbox.bind("<Double-1>", lambda event: self.add_selected_fields())

        left_btns = ttk.Frame(left)
        left_btns.pack(fill=tk.X, pady=4)
        ttk.Button(left_btns, text="全选", command=lambda: self.available_listbox.select_set(0, tk.END)).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_btns, text="清空选择", command=lambda: self.available_listbox.selection_clear(0, tk.END)).pack(side=tk.LEFT, padx=2)

        # 中间：添加/删除按钮
        middle = ttk.Frame(source_frame)
        middle.grid(row=0, column=1, sticky="n", padx=8, pady=28)

        ttk.Button(middle, text="添加 →", command=self.add_selected_fields).pack(fill=tk.X, pady=3)
        ttk.Button(middle, text="← 删除", command=self.remove_order_fields).pack(fill=tk.X, pady=3)
        ttk.Separator(middle, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)
        ttk.Button(middle, text="上移", command=self.move_order_up).pack(fill=tk.X, pady=3)
        ttk.Button(middle, text="下移", command=self.move_order_down).pack(fill=tk.X, pady=3)
        ttk.Button(middle, text="清空", command=self.clear_order_fields).pack(fill=tk.X, pady=3)

        # 右侧：合并顺序列表
        right = ttk.Frame(source_frame)
        right.grid(row=0, column=2, sticky="nsw", padx=(8, 16))

        ttk.Label(right, text="合并顺序：").pack(anchor=tk.W)

        order_frame = ttk.Frame(right)
        order_frame.pack(fill=tk.Y, pady=4)

        self.order_listbox = tk.Listbox(
            order_frame,
            selectmode=tk.EXTENDED,
            height=12,
            width=34,
            exportselection=False
        )
        order_scroll = ttk.Scrollbar(order_frame, orient=tk.VERTICAL, command=self.order_listbox.yview)
        self.order_listbox.configure(yscrollcommand=order_scroll.set)
        self.order_listbox.pack(side=tk.LEFT, fill=tk.Y)
        order_scroll.pack(side=tk.LEFT, fill=tk.Y)
        self.order_listbox.bind("<Delete>", lambda event: self.remove_order_fields())

        # 右侧设置区
        setting = ttk.Frame(source_frame)
        setting.grid(row=0, column=3, sticky="nsew", padx=(8, 0))
        source_frame.columnconfigure(3, weight=1)

        row = 0
        ttk.Label(setting, text="新字段名：").grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(setting, textvariable=self.new_field_var, width=32).grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)

        row += 1
        ttk.Checkbutton(
            setting,
            text="合并前去除每个字段首尾空格",
            variable=self.trim_value_var
        ).grid(row=row, column=0, columnspan=3, sticky=tk.W, padx=4, pady=4)

        row += 1
        ttk.Checkbutton(
            setting,
            text="跳过空值字段，不参与拼接",
            variable=self.skip_empty_var
        ).grid(row=row, column=0, columnspan=3, sticky=tk.W, padx=4, pady=4)

        row += 1
        ttk.Label(setting, text="空值占位符：").grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(setting, textvariable=self.empty_placeholder_var, width=32).grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)
        ttk.Label(setting, text="不跳过空值时可用，例如填 NA").grid(row=row, column=2, sticky=tk.W, padx=4, pady=4)

        row += 1
        ttk.Label(setting, text="预览最大行数：").grid(row=row, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Spinbox(setting, from_=10, to=100000, textvariable=self.preview_limit_var, width=12).grid(row=row, column=1, sticky=tk.W, padx=4, pady=4)

        # 列间隔符设置区
        sep_frame = ttk.LabelFrame(main, text="2. 列间隔符设置：每两列之间可使用不同连接符", padding=8)
        sep_frame.pack(fill=tk.X, pady=8)

        sep_top = ttk.Frame(sep_frame)
        sep_top.pack(fill=tk.X)

        ttk.Label(sep_top, text="批量设为：").pack(side=tk.LEFT, padx=4)
        self.default_separator_combo = ttk.Combobox(
            sep_top,
            textvariable=self.default_separator_var,
            values=self.SEPARATOR_OPTIONS,
            width=12,
            state="readonly"
        )
        self.default_separator_combo.pack(side=tk.LEFT, padx=4)
        self.default_separator_combo.bind("<<ComboboxSelected>>", lambda event: self.update_default_custom_state())

        self.default_separator_custom_entry = ttk.Entry(sep_top, textvariable=self.default_separator_custom_var, width=16)
        self.default_separator_custom_entry.pack(side=tk.LEFT, padx=4)
        ttk.Button(sep_top, text="应用到全部间隔符", command=self.apply_default_separator_to_all).pack(side=tk.LEFT, padx=4)
        ttk.Label(sep_top, text="常用：空字符、空格、换行、制表符、-、_，也可选择“自定义”。").pack(side=tk.LEFT, padx=8)
        ttk.Label(
            sep_frame,
            text="提示：自定义连接符支持 {换行符}、{制表符}、{空格}、{空字符}，也兼容 \\n、\\t，可组合普通文字，如 {换行符}客码:",
            foreground="gray",
            wraplength=1060
        ).pack(anchor=tk.W, padx=4, pady=(6, 0))
        self.update_default_custom_state()

        sep_body = ttk.Frame(sep_frame)
        sep_body.pack(fill=tk.X, pady=6)

        self.sep_canvas = tk.Canvas(sep_body, height=150, highlightthickness=0)
        sep_scroll = ttk.Scrollbar(sep_body, orient=tk.VERTICAL, command=self.sep_canvas.yview)
        self.sep_canvas.configure(yscrollcommand=sep_scroll.set)
        self.sep_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        sep_scroll.pack(side=tk.LEFT, fill=tk.Y)

        self.sep_inner = ttk.Frame(self.sep_canvas)
        self.sep_window_id = self.sep_canvas.create_window((0, 0), window=self.sep_inner, anchor="nw")
        self.sep_inner.bind("<Configure>", self.on_separator_inner_configure)
        self.sep_canvas.bind("<Configure>", self.on_separator_canvas_configure)

        # 操作区
        action = ttk.LabelFrame(main, text="3. 操作", padding=8)
        action.pack(fill=tk.X, pady=8)

        ttk.Button(action, text="预览合并结果", command=self.preview_merge).pack(side=tk.LEFT, padx=4)
        ttk.Button(action, text="执行合并到新列", command=self.apply_merge).pack(side=tk.LEFT, padx=4)
        ttk.Button(action, text="撤销上一次合并", command=self.undo_merge).pack(side=tk.LEFT, padx=4)
        ttk.Separator(action, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(action, text="保存合并模板", command=self.save_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(action, text="载入合并模板", command=self.load_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(action, text="关闭", command=self.window.destroy).pack(side=tk.RIGHT, padx=4)

        ttk.Label(main, textvariable=self.status_var).pack(fill=tk.X, pady=4)

        preview_frame = ttk.LabelFrame(main, text="4. 合并结果预览", padding=8)
        preview_frame.pack(fill=tk.BOTH, expand=True)

        self.preview_tree = ttk.Treeview(preview_frame, show="headings")
        y_scroll = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.preview_tree.yview)
        x_scroll = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=self.preview_tree.xview)
        self.preview_tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.preview_tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        self.rebuild_separator_ui()

    def on_separator_inner_configure(self, event=None):
        self.sep_canvas.configure(scrollregion=self.sep_canvas.bbox("all"))

    def on_separator_canvas_configure(self, event=None):
        if event:
            self.sep_canvas.itemconfigure(self.sep_window_id, width=event.width)

    def refresh_available_fields(self):
        if not hasattr(self, "available_listbox"):
            return
        self.available_listbox.delete(0, tk.END)
        for header in self.app.headers:
            self.available_listbox.insert(tk.END, header)

    def add_selected_fields(self):
        selections = list(self.available_listbox.curselection())
        if not selections:
            messagebox.showinfo("提示", "请先在左侧可选字段中选择字段。")
            return

        existing = set(self.get_order_headers())
        added = 0
        for index in selections:
            header = self.app.headers[index]
            if header in existing:
                continue
            self.order_listbox.insert(tk.END, header)
            existing.add(header)
            added += 1

        if added == 0:
            self.status_var.set("所选字段已经在合并顺序列表中。")
        else:
            self.status_var.set(f"已添加 {added} 个字段到合并顺序列表。")

        self.rebuild_separator_ui()

    def remove_order_fields(self):
        selections = list(self.order_listbox.curselection())
        if not selections:
            return
        for index in reversed(selections):
            self.order_listbox.delete(index)
        self.rebuild_separator_ui()
        self.status_var.set("已从合并顺序中删除选中字段。")

    def clear_order_fields(self):
        self.order_listbox.delete(0, tk.END)
        self.rebuild_separator_ui()
        self.status_var.set("已清空合并顺序。")

    def move_order_up(self):
        selections = list(self.order_listbox.curselection())
        if not selections:
            return

        for index in selections:
            if index <= 0:
                continue
            value = self.order_listbox.get(index)
            self.order_listbox.delete(index)
            self.order_listbox.insert(index - 1, value)

        self.order_listbox.selection_clear(0, tk.END)
        for index in selections:
            self.order_listbox.selection_set(max(0, index - 1))

        self.rebuild_separator_ui()

    def move_order_down(self):
        selections = list(self.order_listbox.curselection())
        if not selections:
            return

        size = self.order_listbox.size()
        for index in reversed(selections):
            if index >= size - 1:
                continue
            value = self.order_listbox.get(index)
            self.order_listbox.delete(index)
            self.order_listbox.insert(index + 1, value)

        self.order_listbox.selection_clear(0, tk.END)
        for index in selections:
            self.order_listbox.selection_set(min(size - 1, index + 1))

        self.rebuild_separator_ui()

    def get_order_headers(self):
        return [self.order_listbox.get(i) for i in range(self.order_listbox.size())]

    def get_order_indices(self):
        indices = []
        missing = []
        for header in self.get_order_headers():
            try:
                indices.append(self.app.headers.index(header))
            except ValueError:
                missing.append(header)
        if missing:
            raise ValueError("以下字段在当前表格中不存在：" + ", ".join(missing))
        return indices

    def parse_separator_text(self, text):
        """把用户可读的特殊分隔符写法转换成真实字符。"""
        value = "" if text is None else str(text)
        replacements = [
            ("{Windows换行}", "\r\n"),
            ("{windows换行}", "\r\n"),
            ("{换行符}", "\n"),
            ("{换行}", "\n"),
            ("{newline}", "\n"),
            ("{NEWLINE}", "\n"),
            ("{制表符}", "\t"),
            ("{tab}", "\t"),
            ("{TAB}", "\t"),
            ("{空格}", " "),
            ("{space}", " "),
            ("{SPACE}", " "),
            ("{空字符}", ""),
            ("{empty}", ""),
            ("{EMPTY}", ""),
        ]
        for key, real in replacements:
            value = value.replace(key, real)
        # 兼容高级用户直接输入的转义写法。
        value = value.replace("\\r\\n", "\r\n")
        value = value.replace("\\n", "\n")
        value = value.replace("\\t", "\t")
        return value

    def separator_to_input_text(self, text):
        """把真实换行/制表符转换成输入框里更容易识别的占位符。"""
        value = "" if text is None else str(text)
        value = value.replace("\r\n", "{Windows换行}")
        value = value.replace("\n", "{换行符}")
        value = value.replace("\t", "{制表符}")
        return value

    def display_to_separator(self, option, custom_value=""):
        if option == "自定义":
            return self.parse_separator_text(custom_value)
        return self.SEPARATOR_MAP.get(option, "")

    def separator_to_display(self, sep):
        for display, value in self.SEPARATOR_MAP.items():
            if value == sep:
                return display, ""
        return "自定义", self.separator_to_input_text(sep)

    def get_separator_raw_text(self, index):
        if index < 0 or index >= len(self.separator_rows):
            return ""
        item = self.separator_rows[index]
        option = item["option_var"].get()
        if option == "自定义":
            return item["custom_var"].get()
        return option

    def preview_separator_pair(self, index, left_name, right_name):
        raw_text = self.get_separator_raw_text(index)
        sep = self.get_current_separators()[index] if index < len(self.get_current_separators()) else ""

        win = tk.Toplevel(self.window)
        win.title("连接符效果预览")
        win.geometry("520x360")
        win.transient(self.window)

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text=f"模拟列数据：{left_name}=A，{right_name}=B").pack(anchor=tk.W, pady=(0, 6))
        ttk.Label(frame, text="用户输入：").pack(anchor=tk.W)
        raw_box = tk.Text(frame, height=4, wrap=tk.WORD)
        raw_box.pack(fill=tk.X, pady=4)
        raw_box.insert("1.0", raw_text)
        raw_box.configure(state="disabled")

        ttk.Label(frame, text="实际合并效果：").pack(anchor=tk.W, pady=(8, 0))
        effect_box = tk.Text(frame, height=7, wrap=tk.WORD)
        effect_box.pack(fill=tk.BOTH, expand=True, pady=4)
        effect_box.insert("1.0", "A" + sep + "B")
        effect_box.configure(state="disabled")

        ttk.Label(frame, text="支持：{换行符}、{制表符}、{空格}、{空字符}，也兼容 \\n、\\t。", foreground="gray").pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(frame, text="关闭", command=win.destroy).pack(anchor=tk.E, pady=(8, 0))

    def get_current_separators(self):
        result = []
        for item in self.separator_rows:
            option = item["option_var"].get()
            custom = item["custom_var"].get()
            result.append(self.display_to_separator(option, custom))
        return result

    def update_default_custom_state(self):
        if not hasattr(self, "default_separator_custom_entry"):
            return
        if self.default_separator_var.get() == "自定义":
            self.default_separator_custom_entry.configure(state="normal")
        else:
            self.default_separator_custom_entry.configure(state="disabled")

    def update_custom_entry_state(self, index):
        if index < 0 or index >= len(self.separator_rows):
            return
        item = self.separator_rows[index]
        if item["option_var"].get() == "自定义":
            item["custom_entry"].configure(state="normal")
        else:
            item["custom_entry"].configure(state="disabled")

    def apply_default_separator_to_all(self):
        option = self.default_separator_var.get()
        custom = self.default_separator_custom_var.get()
        for i, item in enumerate(self.separator_rows):
            item["option_var"].set(option)
            item["custom_var"].set(custom)
            self.update_custom_entry_state(i)
        self.status_var.set("已将批量连接符应用到全部列间隔符。")

    def rebuild_separator_ui(self):
        old_separators = self.get_current_separators() if self.separator_rows else []
        headers = self.get_order_headers() if hasattr(self, "order_listbox") else []

        for child in self.sep_inner.winfo_children():
            child.destroy()
        self.separator_rows = []

        if len(headers) < 2:
            ttk.Label(
                self.sep_inner,
                text="合并顺序少于 2 个字段时，不需要设置列间隔符。"
            ).grid(row=0, column=0, sticky=tk.W, padx=4, pady=6)
            self.sep_canvas.configure(scrollregion=self.sep_canvas.bbox("all"))
            return

        for i in range(len(headers) - 1):
            sep_value = old_separators[i] if i < len(old_separators) else self.display_to_separator(
                self.default_separator_var.get(),
                self.default_separator_custom_var.get()
            )
            option, custom = self.separator_to_display(sep_value)

            option_var = tk.StringVar(value=option)
            custom_var = tk.StringVar(value=custom)

            ttk.Label(
                self.sep_inner,
                text=f"{i + 1}. {headers[i]} 和 {headers[i + 1]} 之间："
            ).grid(row=i, column=0, sticky=tk.W, padx=4, pady=3)

            combo = ttk.Combobox(
                self.sep_inner,
                textvariable=option_var,
                values=self.SEPARATOR_OPTIONS,
                width=12,
                state="readonly"
            )
            combo.grid(row=i, column=1, sticky=tk.W, padx=4, pady=3)

            entry = ttk.Entry(self.sep_inner, textvariable=custom_var, width=24)
            entry.grid(row=i, column=2, sticky=tk.W, padx=4, pady=3)

            preview_btn = ttk.Button(
                self.sep_inner,
                text="预览",
                command=lambda idx=i, left=headers[i], right=headers[i + 1]: self.preview_separator_pair(idx, left, right)
            )
            preview_btn.grid(row=i, column=3, sticky=tk.W, padx=4, pady=3)

            self.separator_rows.append({
                "option_var": option_var,
                "custom_var": custom_var,
                "custom_entry": entry,
            })

            combo.bind("<<ComboboxSelected>>", lambda event, idx=i: self.update_custom_entry_state(idx))
            self.update_custom_entry_state(i)

        self.sep_canvas.configure(scrollregion=self.sep_canvas.bbox("all"))

    def make_unique_header(self, base_name):
        base_name = str(base_name or "合并结果").strip() or "合并结果"
        existing = set(self.app.headers)
        if base_name not in existing:
            return base_name

        i = 2
        while f"{base_name}_{i}" in existing:
            i += 1
        return f"{base_name}_{i}"

    def get_cell_value(self, row, index):
        if index < len(row):
            value = row[index]
        else:
            value = ""

        value = "" if value is None else str(value)

        if self.trim_value_var.get():
            value = value.strip()

        return value

    def build_merged_value_and_status(self, row, selected_indices, separators):
        placeholder = self.empty_placeholder_var.get()
        skip_empty = self.skip_empty_var.get()
        values = [self.get_cell_value(row, index) for index in selected_indices]
        empty_count = sum(1 for value in values if value == "")

        if not values:
            return "", "无字段"

        if skip_empty:
            result = ""
            has_value = False
            for i, value in enumerate(values):
                if value == "":
                    continue
                if not has_value:
                    result = value
                    has_value = True
                else:
                    sep = separators[i - 1] if i - 1 < len(separators) else ""
                    result += sep + value
        else:
            parts = []
            for value in values:
                if value == "":
                    value = placeholder
                parts.append(value)

            result = ""
            for i, part in enumerate(parts):
                if i == 0:
                    result = part
                else:
                    sep = separators[i - 1] if i - 1 < len(separators) else ""
                    result += sep + part

        if empty_count == len(values):
            status = "全部为空"
        elif empty_count > 0:
            status = "部分字段为空"
        else:
            status = "成功"

        return result, status

    def build_merged_value(self, row, selected_indices, separators):
        merged, _status = self.build_merged_value_and_status(row, selected_indices, separators)
        return merged

    def collect_preview_rows(self):
        selected_indices = self.get_order_indices()
        if not selected_indices:
            raise ValueError("请先添加需要合并的字段到右侧合并顺序列表。")

        if not self.app.rows:
            raise ValueError("当前没有可合并的数据行。")

        try:
            limit = int(self.preview_limit_var.get())
        except Exception:
            limit = 500
        if limit <= 0:
            limit = 500

        selected_headers = self.get_order_headers()
        separators = self.get_current_separators()
        if len(separators) < max(0, len(selected_indices) - 1):
            separators += [""] * (len(selected_indices) - 1 - len(separators))

        preview_rows = []
        for row_no, row in enumerate(self.app.rows[:limit], start=1):
            source_values = [self.get_cell_value(row, idx) for idx in selected_indices]
            merged, status = self.build_merged_value_and_status(row, selected_indices, separators)
            preview_rows.append([row_no] + source_values + [merged, status])

        return selected_headers, preview_rows

    def preview_merge(self):
        try:
            selected_headers, preview_rows = self.collect_preview_rows()
        except Exception as e:
            messagebox.showwarning("提示", str(e))
            return

        columns = ["行号"] + selected_headers + ["合并结果", "状态"]
        self.preview_tree.delete(*self.preview_tree.get_children())
        self.preview_tree["columns"] = columns

        for col in columns:
            self.preview_tree.heading(col, text=col)
            self.preview_tree.column(col, width=150, minwidth=80, anchor=tk.W, stretch=False)

        for row in preview_rows:
            self.preview_tree.insert("", tk.END, values=row)

        self.status_var.set(f"已预览 {len(preview_rows)} 行。合并顺序：{' → '.join(selected_headers)}")

    def apply_merge(self):
        try:
            selected_indices = self.get_order_indices()
        except Exception as e:
            messagebox.showwarning("提示", str(e))
            return

        if not selected_indices:
            messagebox.showwarning("提示", "请先添加需要合并的字段到右侧合并顺序列表。")
            return

        if not self.app.rows:
            messagebox.showwarning("提示", "当前没有可合并的数据行。")
            return

        selected_headers = self.get_order_headers()
        separators = self.get_current_separators()
        if len(separators) < max(0, len(selected_indices) - 1):
            separators += [""] * (len(selected_indices) - 1 - len(separators))

        new_header = self.make_unique_header(self.new_field_var.get())

        confirm = messagebox.askyesno(
            "确认合并",
            "将按以下顺序合并字段：\n\n"
            + " → ".join(selected_headers)
            + f"\n\n生成新字段：{new_header}\n\n是否继续？"
        )
        if not confirm:
            return

        self.last_snapshot = (
            list(self.app.headers),
            [list(row) for row in self.app.rows]
        )

        self.app.headers.append(new_header)

        for row in self.app.rows:
            while len(row) < len(self.app.headers) - 1:
                row.append("")
            row.append(self.build_merged_value(row, selected_indices, separators))

        self.app.refresh_tree()
        self.app.info_var.set(f"合并列完成：已生成新字段 {new_header}，共处理 {len(self.app.rows)} 行。")
        self.status_var.set(f"合并完成：已生成新字段 {new_header}。")

        # 主界面字段变化后，刷新左侧字段池；合并顺序保持原字段不变。
        self.refresh_available_fields()
        self.preview_merge()

    def undo_merge(self):
        if not self.last_snapshot:
            messagebox.showinfo("提示", "没有可撤销的合并操作。")
            return

        headers, rows = self.last_snapshot
        self.app.headers = headers
        self.app.rows = rows
        self.app.refresh_tree()
        self.app.info_var.set("已撤销上一次列合并。")
        self.status_var.set("已撤销上一次列合并。")
        self.last_snapshot = None

        self.refresh_available_fields()
        # 移除顺序列表中已不存在的字段。
        existing = set(self.app.headers)
        current = [h for h in self.get_order_headers() if h in existing]
        self.order_listbox.delete(0, tk.END)
        for header in current:
            self.order_listbox.insert(tk.END, header)
        self.rebuild_separator_ui()

        self.preview_tree.delete(*self.preview_tree.get_children())
        self.preview_tree["columns"] = []

    def collect_template(self):
        return {
            "output_field": self.new_field_var.get(),
            "fields": self.get_order_headers(),
            "separators": self.get_current_separators(),
            "skip_empty": self.skip_empty_var.get(),
            "trim_value": self.trim_value_var.get(),
            "empty_placeholder": self.empty_placeholder_var.get(),
            "preview_limit": self.preview_limit_var.get(),
        }

    def apply_template(self, data):
        self.new_field_var.set(data.get("output_field", "合并结果"))
        self.skip_empty_var.set(bool(data.get("skip_empty", False)))
        self.trim_value_var.set(bool(data.get("trim_value", False)))
        self.empty_placeholder_var.set(data.get("empty_placeholder", ""))
        try:
            self.preview_limit_var.set(int(data.get("preview_limit", 500)))
        except Exception:
            self.preview_limit_var.set(500)

        fields = data.get("fields", [])
        existing = set(self.app.headers)
        missing = [field for field in fields if field not in existing]
        valid_fields = [field for field in fields if field in existing]

        self.order_listbox.delete(0, tk.END)
        for field in valid_fields:
            self.order_listbox.insert(tk.END, field)

        # 先重建，再写入模板中的连接符。
        self.rebuild_separator_ui()
        separators = data.get("separators", [])
        for i, sep in enumerate(separators[:len(self.separator_rows)]):
            option, custom = self.separator_to_display(sep)
            self.separator_rows[i]["option_var"].set(option)
            self.separator_rows[i]["custom_var"].set(custom)
            self.update_custom_entry_state(i)

        if missing:
            self.status_var.set("模板已载入，但以下字段不存在，已跳过：" + ", ".join(missing))
        else:
            self.status_var.set("合并模板已载入。")

    def save_template(self):
        path = filedialog.asksaveasfilename(
            title="保存合并规则模板",
            defaultextension=".json",
            filetypes=[("JSON 模板", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return
        try:
            atomic_write_json(path, self.collect_template())
            self.status_var.set(f"已保存合并模板：{path}")
        except Exception as e:
            messagebox.showerror("保存模板失败", str(e))

    def load_template(self):
        path = filedialog.askopenfilename(
            title="载入合并规则模板",
            filetypes=[("JSON 模板", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return
        try:
            data = load_json_file_with_recovery(path, parent=self.window)
            self.apply_template(data)
            self.status_var.set(f"已载入合并模板：{path}")
        except Exception as e:
            messagebox.showerror("载入模板失败", str(e))


class BatchReplaceWindow:
    # 批量替换 / 数据处理窗口

    OPERATORS = ["包含", "不包含", "完全相等", "不等于", "开头是", "结尾是", "为空", "不为空", "正则匹配"]
    REPLACE_MODES = ["局部替换匹配字符串", "整格替换为新值"]
    SCOPES = ["全部行", "当前选中行"]

    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("批量替换 / 数据处理")
        self.window.geometry("1280x760")
        self.window.transient(app.root)

        self.rules = []
        self.preview_changes = []
        self.preview_final_rows = None
        self.last_backup = None

        self.field_var = tk.StringVar(value=app.headers[0] if app.headers else "")
        self.operator_var = tk.StringVar(value="包含")
        self.match_value_var = tk.StringVar()
        self.replace_value_var = tk.StringVar()
        self.replace_mode_var = tk.StringVar(value="局部替换匹配字符串")
        self.scope_var = tk.StringVar(value="全部行")
        self.case_sensitive_var = tk.BooleanVar(value=False)
        self.replace_first_only_var = tk.BooleanVar(value=False)
        self.result_limit_var = tk.StringVar(value="1000")

        self.build_ui()

    def build_ui(self):
        main = ttk.Frame(self.window, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        rule_frame = ttk.LabelFrame(main, text="1. 替换规则设置", padding=8)
        rule_frame.pack(fill=tk.X)

        ttk.Label(rule_frame, text="目标字段：").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
        self.field_combo = ttk.Combobox(rule_frame, textvariable=self.field_var, values=self.app.headers, width=24, state="readonly")
        self.field_combo.grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)

        ttk.Label(rule_frame, text="匹配方式：").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
        ttk.Combobox(rule_frame, textvariable=self.operator_var, values=self.OPERATORS, width=14, state="readonly").grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)

        ttk.Label(rule_frame, text="匹配值：").grid(row=0, column=4, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(rule_frame, textvariable=self.match_value_var, width=28).grid(row=0, column=5, sticky=tk.W, padx=4, pady=4)

        ttk.Label(rule_frame, text="替换值：").grid(row=1, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(rule_frame, textvariable=self.replace_value_var, width=28).grid(row=1, column=1, sticky=tk.W, padx=4, pady=4)

        ttk.Label(rule_frame, text="替换方式：").grid(row=1, column=2, sticky=tk.W, padx=4, pady=4)
        ttk.Combobox(rule_frame, textvariable=self.replace_mode_var, values=self.REPLACE_MODES, width=22, state="readonly").grid(row=1, column=3, sticky=tk.W, padx=4, pady=4)

        ttk.Label(rule_frame, text="作用范围：").grid(row=1, column=4, sticky=tk.W, padx=4, pady=4)
        ttk.Combobox(rule_frame, textvariable=self.scope_var, values=self.SCOPES, width=14, state="readonly").grid(row=1, column=5, sticky=tk.W, padx=4, pady=4)

        ttk.Checkbutton(rule_frame, text="区分大小写", variable=self.case_sensitive_var).grid(row=2, column=1, sticky=tk.W, padx=4, pady=4)
        ttk.Checkbutton(rule_frame, text="只替换第一次出现", variable=self.replace_first_only_var).grid(row=2, column=3, sticky=tk.W, padx=4, pady=4)

        btns = ttk.Frame(rule_frame)
        btns.grid(row=2, column=5, sticky=tk.E, padx=4, pady=4)
        ttk.Button(btns, text="添加当前规则", command=self.add_rule).pack(side=tk.LEFT, padx=3)
        ttk.Button(btns, text="删除选中规则", command=self.delete_selected_rule).pack(side=tk.LEFT, padx=3)
        ttk.Button(btns, text="清空规则", command=self.clear_rules).pack(side=tk.LEFT, padx=3)

        center = ttk.PanedWindow(main, orient=tk.HORIZONTAL)
        center.pack(fill=tk.BOTH, expand=True, pady=8)

        rules_frame = ttk.LabelFrame(center, text="2. 规则列表（为空时，预览/执行会使用上方当前输入规则）", padding=6)
        center.add(rules_frame, weight=1)

        self.rules_tree = ttk.Treeview(
            rules_frame,
            columns=("序号", "字段", "匹配方式", "匹配值", "替换值", "替换方式", "范围", "选项"),
            show="headings",
            height=12
        )
        for col, width in [
            ("序号", 50), ("字段", 120), ("匹配方式", 90), ("匹配值", 150),
            ("替换值", 150), ("替换方式", 150), ("范围", 90), ("选项", 150)
        ]:
            self.rules_tree.heading(col, text=col)
            self.rules_tree.column(col, width=width, anchor=tk.W, stretch=False)

        rules_y = ttk.Scrollbar(rules_frame, orient=tk.VERTICAL, command=self.rules_tree.yview)
        rules_x = ttk.Scrollbar(rules_frame, orient=tk.HORIZONTAL, command=self.rules_tree.xview)
        self.rules_tree.configure(yscrollcommand=rules_y.set, xscrollcommand=rules_x.set)
        self.rules_tree.grid(row=0, column=0, sticky="nsew")
        rules_y.grid(row=0, column=1, sticky="ns")
        rules_x.grid(row=1, column=0, sticky="ew")
        rules_frame.rowconfigure(0, weight=1)
        rules_frame.columnconfigure(0, weight=1)

        preview_frame = ttk.LabelFrame(center, text="3. 替换结果预览", padding=6)
        center.add(preview_frame, weight=2)

        self.preview_tree = ttk.Treeview(
            preview_frame,
            columns=("行号", "字段", "原内容", "新内容", "规则"),
            show="headings",
            height=12
        )
        for col, width in [("行号", 70), ("字段", 120), ("原内容", 260), ("新内容", 260), ("规则", 180)]:
            self.preview_tree.heading(col, text=col)
            self.preview_tree.column(col, width=width, anchor=tk.W, stretch=False)

        prev_y = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.preview_tree.yview)
        prev_x = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=self.preview_tree.xview)
        self.preview_tree.configure(yscrollcommand=prev_y.set, xscrollcommand=prev_x.set)
        self.preview_tree.grid(row=0, column=0, sticky="nsew")
        prev_y.grid(row=0, column=1, sticky="ns")
        prev_x.grid(row=1, column=0, sticky="ew")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)

        bottom = ttk.Frame(main)
        bottom.pack(fill=tk.X)

        ttk.Label(bottom, text="预览最大显示行数：").pack(side=tk.LEFT, padx=4)
        ttk.Entry(bottom, textvariable=self.result_limit_var, width=8).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="预览替换结果", command=self.preview_replace).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="执行替换", command=self.execute_replace).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="撤销上一次替换", command=self.undo_last_replace).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="保存规则模板", command=self.save_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="载入规则模板", command=self.load_template).pack(side=tk.LEFT, padx=4)
        ttk.Button(bottom, text="关闭", command=self.window.destroy).pack(side=tk.RIGHT, padx=4)

        self.status_var = tk.StringVar(value="提示：局部替换会把字段内部匹配到的字符串替换掉，例如 123456 中 45 → 54，结果为 123546。")
        ttk.Label(main, textvariable=self.status_var, padding=(0, 6)).pack(fill=tk.X)

    def normalize_rule(self):
        field = self.field_var.get().strip()
        if field not in self.app.headers:
            raise ValueError("请选择有效的目标字段。")

        operator = self.operator_var.get().strip()
        match_value = self.match_value_var.get()
        replace_value = self.replace_value_var.get()
        replace_mode = self.replace_mode_var.get().strip()

        if operator not in ["为空", "不为空"] and match_value == "":
            raise ValueError("匹配值不能为空。若要判断空值，请选择“为空”或“不为空”。")

        if replace_mode == "局部替换匹配字符串" and operator in ["为空", "不为空"]:
            raise ValueError("“为空/不为空”建议使用“整格替换为新值”，局部替换没有可替换的匹配字符串。")

        return {
            "field": field,
            "operator": operator,
            "match_value": match_value,
            "replace_value": replace_value,
            "replace_mode": replace_mode,
            "scope": self.scope_var.get().strip() or "全部行",
            "case_sensitive": bool(self.case_sensitive_var.get()),
            "replace_first_only": bool(self.replace_first_only_var.get())
        }

    def add_rule(self):
        try:
            rule = self.normalize_rule()
        except Exception as e:
            messagebox.showwarning("规则无效", str(e))
            return

        self.rules.append(rule)
        self.refresh_rules_tree()
        self.status_var.set(f"已添加规则：{len(self.rules)} 条。")

    def delete_selected_rule(self):
        selected = self.rules_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择要删除的规则。")
            return

        indices = sorted([self.rules_tree.index(item) for item in selected], reverse=True)
        for idx in indices:
            if 0 <= idx < len(self.rules):
                self.rules.pop(idx)
        self.refresh_rules_tree()
        self.status_var.set(f"已删除选中规则，剩余 {len(self.rules)} 条。")

    def clear_rules(self):
        self.rules.clear()
        self.refresh_rules_tree()
        self.status_var.set("已清空规则列表。")

    def refresh_rules_tree(self):
        self.rules_tree.delete(*self.rules_tree.get_children())
        for i, rule in enumerate(self.rules, start=1):
            opts = []
            opts.append("区分大小写" if rule.get("case_sensitive") else "忽略大小写")
            opts.append("只替换第一次" if rule.get("replace_first_only") else "替换所有")
            self.rules_tree.insert("", tk.END, values=(
                i,
                rule.get("field", ""),
                rule.get("operator", ""),
                rule.get("match_value", ""),
                rule.get("replace_value", ""),
                rule.get("replace_mode", ""),
                rule.get("scope", "全部行"),
                "；".join(opts)
            ))

    def get_rules_for_action(self):
        if self.rules:
            return list(self.rules)
        return [self.normalize_rule()]

    def get_target_indices(self, scope):
        if scope == "当前选中行":
            selected = self.app.tree.selection()
            if not selected:
                return []
            return sorted({self.app.tree.index(item) for item in selected})
        return list(range(len(self.app.rows)))

    def compare_text(self, text, pattern, rule):
        operator = rule.get("operator", "包含")
        case_sensitive = rule.get("case_sensitive", False)

        text = "" if text is None else str(text)
        pattern = "" if pattern is None else str(pattern)

        if operator == "为空":
            return text == ""
        if operator == "不为空":
            return text != ""

        if operator == "正则匹配":
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                return re.search(pattern, text, flags) is not None
            except re.error as e:
                raise ValueError(f"正则表达式错误：{e}")

        cmp_text = text if case_sensitive else text.lower()
        cmp_pattern = pattern if case_sensitive else pattern.lower()

        if operator == "包含":
            return cmp_pattern in cmp_text
        if operator == "不包含":
            return cmp_pattern not in cmp_text
        if operator == "完全相等":
            return cmp_text == cmp_pattern
        if operator == "不等于":
            return cmp_text != cmp_pattern
        if operator == "开头是":
            return cmp_text.startswith(cmp_pattern)
        if operator == "结尾是":
            return cmp_text.endswith(cmp_pattern)

        return False

    def build_replaced_text(self, text, rule):
        text = "" if text is None else str(text)
        match_value = str(rule.get("match_value", ""))
        replace_value = str(rule.get("replace_value", ""))
        replace_mode = rule.get("replace_mode", "局部替换匹配字符串")
        operator = rule.get("operator", "包含")
        case_sensitive = rule.get("case_sensitive", False)
        count = 1 if rule.get("replace_first_only", False) else 0

        if replace_mode == "整格替换为新值":
            return replace_value

        if operator == "正则匹配":
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                return re.sub(match_value, replace_value, text, count=count, flags=flags)
            except re.error as e:
                raise ValueError(f"正则表达式错误：{e}")

        if match_value == "":
            return text

        if case_sensitive:
            return text.replace(match_value, replace_value, count if count else -1)

        return re.sub(re.escape(match_value), replace_value, text, count=count, flags=re.IGNORECASE)

    def normalize_rows_copy(self):
        normalized = []
        col_count = len(self.app.headers)
        for row in self.app.rows:
            fixed = list(row)
            if len(fixed) < col_count:
                fixed += [""] * (col_count - len(fixed))
            if len(fixed) > col_count:
                fixed = fixed[:col_count]
            normalized.append(fixed)
        return normalized

    def compute_changes(self):
        rules = self.get_rules_for_action()
        final_rows = self.normalize_rows_copy()
        changes = []

        for rule_index, rule in enumerate(rules, start=1):
            field = rule.get("field")
            if field not in self.app.headers:
                continue

            col_idx = self.app.headers.index(field)
            target_indices = self.get_target_indices(rule.get("scope", "全部行"))

            for row_idx in target_indices:
                if row_idx < 0 or row_idx >= len(final_rows):
                    continue

                old_value = final_rows[row_idx][col_idx]
                if self.compare_text(old_value, rule.get("match_value", ""), rule):
                    new_value = self.build_replaced_text(old_value, rule)
                    if new_value != old_value:
                        changes.append({
                            "row_index": row_idx,
                            "field": field,
                            "old": old_value,
                            "new": new_value,
                            "rule_index": rule_index,
                            "rule": rule
                        })
                        final_rows[row_idx][col_idx] = new_value

        return changes, final_rows

    def get_preview_limit(self):
        try:
            value = int(self.result_limit_var.get().strip())
            return max(value, 1)
        except Exception:
            return 1000

    def preview_replace(self):
        try:
            changes, final_rows = self.compute_changes()
        except Exception as e:
            messagebox.showerror("预览失败", str(e))
            return

        self.preview_changes = changes
        self.preview_final_rows = final_rows
        self.preview_tree.delete(*self.preview_tree.get_children())

        limit = self.get_preview_limit()
        for change in changes[:limit]:
            self.preview_tree.insert("", tk.END, values=(
                change["row_index"] + 1,
                change["field"],
                change["old"],
                change["new"],
                f"规则{change['rule_index']}"
            ))

        if not changes:
            self.status_var.set("没有找到可替换的数据。")
        else:
            suffix = f"，仅显示前 {limit} 条" if len(changes) > limit else ""
            self.status_var.set(f"预览完成：共 {len(changes)} 处变更{suffix}。")

    def execute_replace(self):
        try:
            changes, final_rows = self.compute_changes()
        except Exception as e:
            messagebox.showerror("执行失败", str(e))
            return

        if not changes:
            messagebox.showinfo("提示", "没有找到可替换的数据。")
            return

        ok = messagebox.askyesno("确认替换", f"本次将修改 {len(changes)} 处内容。\n是否继续？")
        if not ok:
            return

        self.last_backup = [list(row) for row in self.app.rows]
        self.app.rows = final_rows
        self.app.refresh_tree()

        self.preview_changes = changes
        self.preview_final_rows = final_rows
        self.preview_tree.delete(*self.preview_tree.get_children())
        limit = self.get_preview_limit()
        for change in changes[:limit]:
            self.preview_tree.insert("", tk.END, values=(
                change["row_index"] + 1,
                change["field"],
                change["old"],
                change["new"],
                f"规则{change['rule_index']}"
            ))

        self.app.info_var.set(f"批量替换完成：共修改 {len(changes)} 处内容。")
        self.status_var.set(f"执行完成：共修改 {len(changes)} 处内容。可点击“撤销上一次替换”恢复。")

    def undo_last_replace(self):
        if self.last_backup is None:
            messagebox.showwarning("提示", "当前没有可撤销的替换操作。")
            return

        self.app.rows = [list(row) for row in self.last_backup]
        self.app.refresh_tree()
        self.last_backup = None
        self.preview_tree.delete(*self.preview_tree.get_children())
        self.status_var.set("已撤销上一次替换操作。")
        self.app.info_var.set("已撤销上一次批量替换。")

    def save_template(self):
        rules = self.rules
        if not rules:
            try:
                rules = [self.normalize_rule()]
            except Exception as e:
                messagebox.showwarning("规则无效", str(e))
                return

        path = filedialog.asksaveasfilename(
            title="保存替换规则模板",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return

        data = {
            "version": 1,
            "type": "batch_replace_template",
            "rules": rules
        }
        try:
            atomic_write_json(path, data)
            self.status_var.set(f"已保存替换规则模板：{path}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def load_template(self):
        path = filedialog.askopenfilename(
            title="载入替换规则模板",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return

        try:
            data = load_json_file_with_recovery(path, parent=self.window)

            rules = data.get("rules", data if isinstance(data, list) else [])
            valid_rules = []
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                if rule.get("field") in self.app.headers:
                    valid_rules.append({
                        "field": rule.get("field", ""),
                        "operator": rule.get("operator", "包含"),
                        "match_value": rule.get("match_value", ""),
                        "replace_value": rule.get("replace_value", ""),
                        "replace_mode": rule.get("replace_mode", "局部替换匹配字符串"),
                        "scope": rule.get("scope", "全部行"),
                        "case_sensitive": bool(rule.get("case_sensitive", False)),
                        "replace_first_only": bool(rule.get("replace_first_only", False))
                    })

            self.rules = valid_rules
            self.refresh_rules_tree()
            self.status_var.set(f"已载入模板：{path}，有效规则 {len(valid_rules)} 条。")
        except Exception as e:
            messagebox.showerror("载入失败", str(e))

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
        state = workflow_filter_advanced_filter_valid_state(
            self.conditions,
            self.join_rules,
            self.output_fields,
            self.field_display_cache,
        )
        self.conditions = state["conditions"]
        self.join_rules = state["join_rules"]
        self.output_fields = state["output_fields"]

        self.refresh_conditions_tree()
        self.refresh_join_tree()
        self.refresh_output_fields_listbox()

    def add_condition(self):
        field = self.filter_field_var.get().strip()
        op = self.filter_operator_var.get().strip()
        value = self.filter_value_var.get()

        if not field:
            messagebox.showwarning("提示", "请选择筛选字段。")
            return

        if op not in ["为空", "不为空"] and value == "":
            if not messagebox.askyesno("确认", "当前条件值为空，是否继续添加？"):
                return

        self.conditions = workflow_add_advanced_filter_condition(
            self.conditions,
            field,
            op,
            value,
        )

        self.refresh_conditions_tree()
        self.filter_value_var.set("")

    def delete_selected_condition(self):
        selections = list(self.conditions_tree.selection())
        if not selections:
            return

        indexes = [self.conditions_tree.index(item) for item in selections]
        self.conditions = workflow_remove_advanced_filter_items_by_indexes(
            self.conditions,
            indexes,
        )

        self.refresh_conditions_tree()

    def clear_conditions(self):
        self.conditions = workflow_clear_advanced_filter_items()
        self.refresh_conditions_tree()

    def refresh_conditions_tree(self):
        self.conditions_tree.delete(*self.conditions_tree.get_children())
        for cond in self.conditions:
            self.conditions_tree.insert(
                "",
                tk.END,
                values=(cond["field"], cond["op"], cond["value"])
            )

    def add_join_rule(self):
        left = self.join_left_var.get().strip()
        op = self.join_operator_var.get().strip()
        right = self.join_right_var.get().strip()

        if not left or not right:
            messagebox.showwarning("提示", "请选择左右匹配字段。")
            return

        if left == right:
            if not messagebox.askyesno("确认", "左右字段相同，是否仍然添加？"):
                return

        self.join_rules = workflow_add_advanced_filter_join_rule(
            self.join_rules,
            left,
            op,
            right,
        )

        self.refresh_join_tree()

    def delete_selected_join_rule(self):
        selections = list(self.join_tree.selection())
        if not selections:
            return

        indexes = [self.join_tree.index(item) for item in selections]
        self.join_rules = workflow_remove_advanced_filter_items_by_indexes(
            self.join_rules,
            indexes,
        )

        self.refresh_join_tree()

    def clear_join_rules(self):
        self.join_rules = workflow_clear_advanced_filter_items()
        self.refresh_join_tree()

    def refresh_join_tree(self):
        self.join_tree.delete(*self.join_tree.get_children())
        for rule in self.join_rules:
            self.join_tree.insert(
                "",
                tk.END,
                values=(rule["left"], rule["op"], rule["right"])
            )

    def add_output_fields(self):
        selections = list(self.available_fields_listbox.curselection())
        if not selections:
            return

        self.output_fields = workflow_add_advanced_filter_output_fields(
            self.output_fields,
            self.field_display_cache,
            selections,
        )

        self.refresh_output_fields_listbox()

    def add_all_output_fields(self):
        self.output_fields = workflow_add_all_advanced_filter_output_fields(
            self.output_fields,
            self.field_display_cache,
        )

        self.refresh_output_fields_listbox()

    def remove_output_fields(self):
        selections = list(self.output_fields_listbox.curselection())
        if not selections:
            return

        self.output_fields = workflow_remove_advanced_filter_output_fields(
            self.output_fields,
            selections,
        )

        self.refresh_output_fields_listbox()

    def clear_output_fields(self):
        self.output_fields = []
        self.refresh_output_fields_listbox()

    def refresh_output_fields_listbox(self):
        self.output_fields_listbox.delete(0, tk.END)
        for field in self.output_fields:
            self.output_fields_listbox.insert(tk.END, field)

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

        self.app.headers = self.preview_headers[:]
        self.app.rows = [row[:] for row in self.preview_rows]
        self.app.raw_data = ""
        self.app.refresh_tree()
        self.app.info_var.set(
            f"已从高级筛选载入预览结果：{len(self.app.rows)} 行 × {len(self.app.headers)} 列。"
        )

    def save_result_to_table(self):
        if not self.preview_headers:
            self.preview_result()

        if not self.preview_headers:
            return

        save_name = self.save_table_var.get().strip()
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


class PlanWorkflowWindow(
    PlanWorkflowUiMixin,
    PlanPreviewMixin,
    WorkflowConfigBuilderMixin,
    WorkflowJumpMixin,
    WorkflowControlRuntimeMixin,
    WorkflowPluginRuntimeMixin,
    WorkflowTableRuntimeMixin,
    WorkflowOutputRuntimeMixin,
    PluginConfigWindowMixin,
    FilterConfigWindowMixin,
    GroupConfigWindowMixin,
    TableAccessWindowMixin,
    WorkflowExecutionMixin,
    WorkflowNodeExecutionMixin,
):
    """
    计划 / 工作流处理窗口。

    设计目标：
    1. 把批量替换、数据提取、合并列、高级筛选、删除列、移动列作为节点串联。
    2. 每个节点都接收 headers / rows，输出新的 headers / rows。
    3. 支持预览到当前节点、预览完整计划、输出到主界面或保存到 SQLite。

    说明：
    - 计划内的“高级筛选”支持以上一步结果作为“当前表”，再选择数据库中的其他表进行多表匹配。
    """

    NODE_TYPES = ["获取文件列表", "节点组 / 子工作流", "循环执行起点", "跳转锚点节点", "无条件跳转节点", "条件判断节点", "条件跳转节点", "批量替换", "数据提取", "格式规范化 / 日期时间解析", "新建日期时间列", "新建列", "合并列", "批量更改列名", "去重 / 重复数据处理", "列数字运算", "匹配值输出列名", "复制列", "复制行", "删除行", "填充值", "序列填充", "区域填充", "行数据映射填充", "保存中转数据", "选定列写入指定表", "字段映射写入表", "高级筛选", "删除列", "移动列", "批量重命名", "循环判断回跳"]
    TABLE_ACCESS_POLICY_CHOICES = ["只审计", "预检确认", "强制拦截"]
    MAX_EXPANDED_ROWS = 200000
    MAX_TARGET_CELLS = 1000000
    TABLE_ACCESS_POLICY_DISPLAY = {
        "audit": "只审计",
        "prompt": "预检确认",
        "strict": "强制拦截",
        "off": "关闭",
    }
    STANDARD_WRITE_MODE_CHOICES = [
        "",
        "current_table_default",
        "create_new",
        "append",
        "overlay_by_order",
        "update_by_key",
        "upsert_by_key",
        "clear_keep_schema",
        "keep_schema_insert",
        "replace_table",
        "timestamp_new",
        "fail_if_exists",
        "write_fields_only",
        "fill_blank_fields",
    ]
    LOGIC_TYPES = ["AND", "OR"]
    FILTER_OPS = ["等于", "不等于", "包含", "不包含", "开头是", "结尾是", "大于", "小于", "大于等于", "小于等于", "为空", "不为空", "正则匹配"]
    FILTER_VALUE_SOURCES = ["固定值", "字段值"]
    REPLACE_MATCH_MODES = ["包含", "完全相等", "开头是", "结尾是", "正则匹配", "为空", "不为空"]
    REPLACE_MODES = ["局部替换匹配字符串", "整格替换为新值"]
    REPLACE_VALUE_SOURCES = ["手动输入", "列字段"]
    REPLACE_ROW_POLICIES = ["当前行", "第一行", "固定行号", "按匹配行号", "按命中序号"]
    EXTRACT_METHODS = [
        "正则提取", "固定位置提取", "从左取N位", "从右取N位", "按分隔符提取",
        "前后关键字之间提取", "指定字符前提取", "指定字符后提取", "删除前缀", "删除后缀"
    ]
    OUTPUT_MODES = ["生成新字段", "覆盖源字段"]
    UNMATCHED_MODES = ["留空", "保留原值", "填写固定值", "跳过该行"]
    FORMAT_PARSE_TYPES = ["日期", "时间", "日期时间"]
    FORMAT_INPUT_STRUCTURES = ["固定位置", "分隔符", "自动识别常见格式"]
    FORMAT_YEAR_RULES = ["20xx", "19xx", "自动窗口", "不补全"]
    FORMAT_DATE_ORDERS = ["年-月-日", "月-日-年", "日-月-年"]
    FORMAT_OUTPUT_MODES = ["生成新字段", "覆盖源字段", "生成多个字段"]
    CURRENT_DATETIME_OUTPUT_MODES = ["生成新字段", "覆盖已有字段"]
    CURRENT_DATETIME_TIME_MODES = ["整次运行固定同一时间", "逐行实时获取"]
    CURRENT_DATETIME_FORMAT_MODES = ["占位符模板", "Python strftime"]
    NEW_COLUMNS_CONFLICT_MODES = ["自动改名", "跳过已有字段", "覆盖已有字段", "存在则报错"]
    NEW_COLUMNS_VALUE_MODES = ["统一默认值", "按列配置值", "空值"]
    SEPARATOR_OPTIONS = ["空字符", "空格", "换行", "Windows换行", "制表符", "-", "_", "/", "\\", "|", ",", ";", ":", ".", "+", "自定义"]

    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("计划 / 工作流处理")
        self.window.geometry("1680x950")
        self.window.minsize(1050, 650)
        self.window.transient(app.root)

        self.nodes = []
        self.preview_headers = list(app.headers)
        self.preview_rows = [list(row) for row in app.rows]
        self.current_config_widgets = {}
        self.separator_widgets = []
        self.field_listbox = None
        self.status_var = tk.StringVar(value="计划窗口已打开。先添加节点，再预览或执行完整计划。")
        self.output_mode_var = tk.StringVar(value="输出到主界面预览区")
        self.output_table_var = tk.StringVar(value=self.make_default_output_table_name())
        self.backup_before_overwrite_var = tk.BooleanVar(value=True)
        self.table_access_policy_var = tk.StringVar(value="只审计")
        self.node_type_var = tk.StringVar(value=self.NODE_TYPES[0])
        self.selected_node_index = None
        self.preview_edit_mode = False
        self.preview_edit_entry = None
        self.preview_edit_btn_text = tk.StringVar(value="修改模式:关")
        self.preview_dirty = False
        self.current_transit_tables = {}
        self.last_workflow_context = {}
        self.last_table_access_logs = []
        self.last_table_access_precheck = []
        # “当前预览结果”独立缓存：结果预览区临时载入 SQLite/中转/主界面表时，
        # 不应覆盖最后一次计划预览/执行得到的结果，否则下拉切换后会丢失原预览结果。
        self.plan_preview_headers = list(self.preview_headers)
        self.plan_preview_rows = [list(row) for row in self.preview_rows]
        self.preview_view_kind = "preview"
        # 结果预览区表格选择：用于快速查看当前预览、主界面表、SQLite表和中转副表。
        self.preview_table_var = tk.StringVar(value="当前预览结果")
        self.preview_table_map = {}
        self.preview_search_var = tk.StringVar(value="")
        self.preview_search_matches = []
        self.preview_search_index = -1

        # 循环单步调试缓存：在“循环判断回跳”节点点击“执行循环一次”时复用。
        # 用于逐次运行循环体，后续预览节点可接着这个 N 次循环后的上下文继续执行。
        self.manual_loop_context = None
        self.manual_loop_headers = None
        self.manual_loop_rows = None
        self.manual_loop_start_idx = None
        self.manual_loop_judge_idx = None
        self.manual_loop_after_index = None
        self.manual_loop_logs = []

        # 后台执行/进度条状态：主界面不直接跑耗时流程，后台线程负责执行，Queue 回传进度。
        # 第一版采用线程 worker，接口按“可迁移到子进程 worker”的消息协议设计。
        self.workflow_worker_thread = None
        self.workflow_worker_queue = queue.Queue()
        self.workflow_worker_cancel = None
        self.workflow_worker_running = False
        self.workflow_progress_var = tk.DoubleVar(value=0)
        self.node_progress_var = tk.DoubleVar(value=0)
        self.workflow_progress_text = tk.StringVar(value="总进度：空闲")
        self.node_progress_text = tk.StringVar(value="当前节点：空闲")
        self.worker_status_text = tk.StringVar(value="执行状态：空闲")
        self.workflow_current_task = None
        self.workflow_widget_state_backup = {}
        self.workflow_cancel_button = None

        # 外部插件节点：启动/打开计划窗口时扫描 plugins 目录并注册。
        self.plugin_registry = {}
        self.plugin_display_map = {}
        self.plugin_load_errors = []
        self.load_plugins(show_status=False)

        # 计划模板库：程序真实目录下的 plan 文件夹。
        # 只识别 template_type == "workflow_plan" 的新版模板。
        self.plan_dir = self.get_plan_dir()
        # 节点组模板库：程序真实目录下的 groups 文件夹。
        self.group_dir = self.get_group_dir()
        self.plan_template_var = tk.StringVar(value="")
        self.plan_template_map = {}

        self.build_ui()
        self.refresh_node_list()
        self.refresh_preview_tree(self.preview_headers, self.preview_rows)
        self.refresh_plan_template_list(show_status=False)

    def make_default_output_table_name(self):
        base = self.app.sanitize_sql_name(self.app.table_name_var.get(), "计划结果")
        return f"{base}_计划结果_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def normalize_table_access_policy(self, value=None):
        if value is None:
            value = self.table_access_policy_var.get()
        return TableAccessManager.normalize_permission_policy(value)

    def table_access_policy_display(self, value=None):
        policy = self.normalize_table_access_policy(value)
        return self.TABLE_ACCESS_POLICY_DISPLAY.get(policy, "只审计")

    def set_table_access_policy(self, value):
        self.table_access_policy_var.set(self.table_access_policy_display(value))

    def normalize_table_access_write_mode(self, mode):
        return TableAccessManager.normalize_write_mode(mode)

    def write_mode_permission_set(self, mode, exists=False, read=False, partial=False):
        perms = {key: False for key, _ in self.table_access_permission_items()}
        for key in TableAccessManager.required_permissions_for_write_mode(mode, exists=exists, partial=partial):
            if key in perms:
                perms[key] = True
        if read:
            perms["read_table"] = True
        return perms

    def write_mode_display_text(self, mode):
        standard = self.normalize_table_access_write_mode(mode)
        labels = {
            "": "",
            "current_table_default": "当前表默认",
            "create_new": "新建表写入",
            "append": "追加行",
            "overlay_by_order": "按顺序覆盖",
            "update_by_key": "按键更新",
            "upsert_by_key": "匹配更新或追加",
            "clear_keep_schema": "清空保留结构写入",
            "keep_schema_insert": "保留结构写入",
            "replace_table": "替换整表",
            "timestamp_new": "自动时间戳新表",
            "fail_if_exists": "存在则报错",
            "write_fields_only": "指定字段写入",
            "fill_blank_fields": "字段空缺补齐",
        }
        return labels.get(standard, str(mode or ""))

    def _on_config_frame_configure(self, event=None):
        """更新节点配置区滚动范围。"""
        if hasattr(self, "config_canvas"):
            self.config_canvas.configure(scrollregion=self.config_canvas.bbox("all"))

    def _on_config_canvas_configure(self, event=None):
        """让内部配置区域宽度跟随 Canvas，减少横向截断。"""
        if hasattr(self, "config_canvas") and hasattr(self, "config_canvas_window"):
            try:
                self.config_canvas.itemconfigure(self.config_canvas_window, width=event.width)
            except Exception:
                pass

    def _bind_config_mousewheel(self, event=None):
        if hasattr(self, "config_canvas"):
            self.config_canvas.bind_all("<MouseWheel>", self._on_config_mousewheel)
            self.config_canvas.bind_all("<Shift-MouseWheel>", self._on_config_shift_mousewheel)

    def _unbind_config_mousewheel(self, event=None):
        if hasattr(self, "config_canvas"):
            self.config_canvas.unbind_all("<MouseWheel>")
            self.config_canvas.unbind_all("<Shift-MouseWheel>")

    def _on_config_mousewheel(self, event):
        if hasattr(self, "config_canvas"):
            self.config_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_config_shift_mousewheel(self, event):
        if hasattr(self, "config_canvas"):
            self.config_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

    def show_empty_config(self):
        self.clear_config_frame()
        ttk.Label(self.config_frame, text="请先添加并选择一个节点。每个节点会接收上一步结果，并输出给下一步。", foreground="gray").pack(anchor=tk.W)

    def clear_config_frame(self):
        for child in self.config_frame.winfo_children():
            child.destroy()
        self.current_config_widgets = {}
        self.separator_widgets = []
        self.field_listbox = None
        if hasattr(self, "config_canvas"):
            self.config_canvas.yview_moveto(0)
            self.config_canvas.xview_moveto(0)
            self.config_canvas.after_idle(lambda: self.config_canvas.configure(scrollregion=self.config_canvas.bbox("all")))

    def get_selected_node_index(self):
        sel = self.node_listbox.curselection()
        if not sel:
            return None
        return sel[0]

    def on_node_select(self, event=None):
        idx = self.get_selected_node_index()
        self.selected_node_index = idx
        self.rebuild_current_config()

    def rebuild_current_config(self):
        idx = self.get_selected_node_index()
        if idx is None or idx < 0 or idx >= len(self.nodes):
            self.show_empty_config()
            return
        self.build_node_config(idx)

    def refresh_node_list(self, select_index=None, reveal=True):
        self.ensure_node_tree_identity(self.nodes)
        selected = self.get_selected_node_index() if select_index is None else select_index
        self.node_listbox.delete(0, tk.END)
        for idx, node in enumerate(self.nodes, start=1):
            mark = "√" if node.get("enabled", True) else "×"
            self.node_listbox.insert(tk.END, f"[{mark}] {idx}. {node.get('type')}：{node.get('name', '')}")
        if selected is not None and self.nodes:
            selected = min(selected, len(self.nodes) - 1)
            self.selected_node_index = selected
            self.node_listbox.selection_clear(0, tk.END)
            self.node_listbox.selection_set(selected)
            self.node_listbox.activate(selected)
            if reveal:
                self.node_listbox.see(selected)
        elif not self.nodes:
            self.selected_node_index = None


    # ------------------------------------------------------------------
    # 外部 Python 插件节点
    # ------------------------------------------------------------------
    def get_plugins_dir(self):
        path = os.path.join(getattr(self.app, "app_dir", get_app_dir()), "plugins")
        os.makedirs(path, exist_ok=True)
        return path

    def get_plugin_data_dir(self, plugin_id=None):
        base = os.path.join(getattr(self.app, "app_dir", get_app_dir()), "plugin_data")
        if plugin_id:
            base = os.path.join(base, self.app.sanitize_sql_name(plugin_id, "plugin"))
        os.makedirs(base, exist_ok=True)
        return base

    def get_plugin_log_dir(self):
        path = os.path.join(getattr(self.app, "app_dir", get_app_dir()), "logs", "plugins")
        os.makedirs(path, exist_ok=True)
        return path

    def get_plugin_env_dir(self, plugin_id=None):
        base = os.path.join(getattr(self.app, "app_dir", get_app_dir()), "plugin_envs")
        if plugin_id:
            base = os.path.join(base, self.app.sanitize_sql_name(plugin_id, "plugin"))
        os.makedirs(base, exist_ok=True)
        return base

    def get_node_type_values(self):
        values = list(self.NODE_TYPES)
        values.extend(sorted(getattr(self, "plugin_display_map", {}).keys()))
        return values

    def refresh_plugins(self):
        self.load_plugins(show_status=True)
        if hasattr(self, "node_type_combo"):
            self.node_type_combo["values"] = self.get_node_type_values()
        if self.node_type_var.get() not in self.get_node_type_values():
            self.node_type_var.set(self.NODE_TYPES[0])
        self.rebuild_current_config()

    def load_plugins(self, show_status=False):
        """扫描 plugins 目录并注册插件。"""
        self.plugin_registry = {}
        self.plugin_display_map = {}
        self.plugin_load_errors = []
        plugins_dir = self.get_plugins_dir()
        registry, errors = scan_plugins(plugins_dir)
        self.plugin_registry = registry
        self.plugin_load_errors = errors

        used_names = {}
        external_only_count = 0
        for plugin_id, item in sorted(self.plugin_registry.items(), key=lambda kv: kv[1]["info"].get("name", kv[0])):
            name = str(item["info"].get("name", plugin_id)).strip() or plugin_id
            suffix = ""
            if item.get("load_status") == "仅独立环境运行":
                external_only_count += 1
                suffix = " [仅独立]"
            display = f"插件 / {name}{suffix}"
            if display in used_names:
                used_names[display] += 1
                display = f"插件 / {name} ({plugin_id}){suffix}"
            else:
                used_names[display] = 1
            self.plugin_display_map[display] = plugin_id

        if show_status:
            msg = f"插件刷新完成：已注册 {len(self.plugin_registry)} 个插件"
            if external_only_count:
                msg += f"，其中仅独立环境 {external_only_count} 个"
            if self.plugin_load_errors:
                msg += f"，加载失败 {len(self.plugin_load_errors)} 个"
                first = self.plugin_load_errors[0]
                msg += f"；示例：{first.get('file')} - {first.get('error')}"
            self.status_var.set(msg)


    def default_config_for_plugin(self, plugin_id):
        item = self.plugin_registry.get(plugin_id, {})
        schema = item.get("schema", [])
        params = {}
        for field in schema:
            if not isinstance(field, dict):
                continue
            name = field.get("name")
            if not name:
                continue
            default = field.get("default", "")
            if field.get("type") == "multi_field_select" and default == "":
                default = []
            params[name] = default
        info = item.get("info", {})
        default_run_mode = info.get("run_mode") or item.get("run_mode_default") or "主程序内置环境"
        if default_run_mode in ("external_python", "独立环境", "插件独立环境"):
            default_run_mode = "插件独立环境"
        else:
            default_run_mode = "主程序内置环境"
        return {
            "plugin_id": plugin_id,
            "params": params,
            "input_tables": [],
            "run_mode": default_run_mode,
            "external_python": "",
            "external_env_dir": self.get_plugin_env_dir(plugin_id),
            "external_entry": item.get("external_entry", item.get("path", "")),
            "external_timeout": "0",
            "output_mode": "使用插件返回结果",
            "save_output_as_transit": False,
            "transit_name": item.get("info", {}).get("name", plugin_id),
            "transit_conflict_mode": "覆盖",
            "save_plugin_log_file": True,
            "save_plugin_log_sqlite": False,
            "save_plugin_log_transit": False,
            "plugin_log_transit_name": f"{item.get('info', {}).get('name', plugin_id)}_日志",
            "plugin_log_in_preview": False,
            "plugin_failure_policy": "停止工作流",
        }

    def get_sqlite_table_names(self):
        db_path = self.app.db_path_var.get().strip()
        if not db_path or not os.path.exists(db_path):
            return []
        try:
            return TableAccessManager(db_path).list_tables()
        except Exception:
            return []

    def get_workflow_snapshot(self, context=None):
        """返回后台任务快照。后台线程优先使用快照，避免直接读取 Tkinter 变量。"""
        if isinstance(context, dict):
            snapshot = context.get("workflow_snapshot") or {}
            if isinstance(snapshot, dict):
                return snapshot
        return {}

    def get_workflow_db_path(self, context=None):
        """执行期统一获取 SQLite 路径：优先读 workflow_snapshot，兜底读主线程 UI 变量。"""
        snapshot = self.get_workflow_snapshot(context)
        db_path = str(snapshot.get("db_path") or "").strip()
        if db_path:
            return db_path
        try:
            return self.app.db_path_var.get().strip()
        except Exception:
            return ""

    def make_node_id(self):
        return "node_" + uuid.uuid4().hex[:12]

    def table_permission_set(self, read=False, write=False, create=False, append=False, update=False,
                             clear=False, replace=False, alter=False, delete=False, drop=False):
        return {
            "read_table": bool(read),
            "write_table": bool(write),
            "create_table": bool(create),
            "append_rows": bool(append),
            "update_rows": bool(update),
            "clear_table": bool(clear),
            "replace_table": bool(replace),
            "alter_schema": bool(alter),
            "delete_rows": bool(delete),
            "drop_table": bool(drop),
        }

    def make_table_access_entry(self, role, table, source_type="SQLite表", is_current_table=False,
                                permissions=None, write_mode="", field_mapping=None, log_only=False,
                                table_pattern="", pattern_type="glob", declared_by=""):
        return {
            "role": role,
            "table": table,
            "table_pattern": str(table_pattern or "").strip(),
            "pattern_type": str(pattern_type or "glob").strip(),
            "declared_by": str(declared_by or "").strip(),
            "source_type": source_type,
            "is_current_table": bool(is_current_table),
            "permissions": permissions or self.table_permission_set(read=True),
            "write_mode": self.normalize_table_access_write_mode(write_mode),
            "field_mapping_mode": "by_name",
            "field_mapping": field_mapping or {},
            "log_only": bool(log_only),
        }

    def get_plugin_table_access_specs(self, config):
        config = config or {}
        plugin_id = str(config.get("plugin_id", "") or "").strip()
        item = self.plugin_registry.get(plugin_id, {}) if hasattr(self, "plugin_registry") else {}
        module = item.get("module")
        params = dict(config.get("params", {}) or {})
        specs = None
        provider = getattr(module, "get_table_access_spec", None) if module is not None else None
        if callable(provider):
            try:
                specs = provider(params, {"plugin_id": plugin_id, "config_probe": True})
            except TypeError:
                specs = provider(params)
            except Exception:
                specs = None
        if specs is None:
            info = item.get("info", {}) or {}
            specs = info.get("table_access") or info.get("table_access_spec") or []
        if isinstance(specs, dict):
            specs = specs.get("tables") or [specs]
        return [spec for spec in (specs or []) if isinstance(spec, dict)]

    def plugin_has_table_access_declaration(self, config):
        config = config or {}
        plugin_id = str(config.get("plugin_id", "") or "").strip()
        item = self.plugin_registry.get(plugin_id, {}) if hasattr(self, "plugin_registry") else {}
        module = item.get("module")
        if callable(getattr(module, "get_table_access_spec", None)):
            return True
        info = item.get("info", {}) or {}
        return bool(info.get("table_access") or info.get("table_access_spec"))

    def plugin_needs_table_access_declaration(self, config):
        config = config or {}
        plugin_id = str(config.get("plugin_id", "") or "").strip()
        item = self.plugin_registry.get(plugin_id, {}) if hasattr(self, "plugin_registry") else {}
        info = item.get("info", {}) or {}
        danger = str(info.get("danger_level", "") or "").strip().lower()
        return danger in {"db_write", "database_write"} or bool(info.get("database_requests"))

    def make_plugin_declared_access_entry(self, plugin_id, spec):
        spec = spec or {}
        permissions = {key: False for key, _ in self.table_access_permission_items()}
        permissions.update({
            key: bool(value)
            for key, value in (spec.get("permissions") or {}).items()
            if key in permissions
        })
        return self.make_table_access_entry(
            spec.get("role") or "plugin_declared",
            spec.get("table") or "",
            source_type=spec.get("source_type") or "SQLite表",
            is_current_table=bool(spec.get("is_current_table")),
            permissions=permissions,
            write_mode=spec.get("write_mode") or "",
            field_mapping=copy.deepcopy(spec.get("field_mapping") or {}),
            log_only=bool(spec.get("log_only")),
            table_pattern=spec.get("table_pattern") or "",
            pattern_type=spec.get("pattern_type") or "glob",
            declared_by=plugin_id,
        )

    def default_table_access_for_node(self, node):
        return workflow_build_default_table_access_for_node(
            node,
            self.make_table_access_entry,
            self.table_permission_set,
            normalize_selected_columns_write_mode=getattr(self, "normalize_selected_columns_write_mode", None),
            normalize_group_transit_conflict_mode=getattr(self, "normalize_group_transit_conflict_mode", None),
            get_plugin_table_access_specs=self.get_plugin_table_access_specs,
            make_plugin_declared_access_entry=self.make_plugin_declared_access_entry,
        )

    def ensure_node_identity(self, node, force_new=False):
        if not isinstance(node, dict):
            return node
        if force_new or not str(node.get("node_id", "")).strip():
            node["node_id"] = self.make_node_id()
        if not isinstance(node.get("table_access"), dict):
            node["table_access"] = self.default_table_access_for_node(node)
        return node

    def ensure_node_tree_identity(self, nodes, force_new=False):
        for node in nodes or []:
            self.ensure_node_identity(node, force_new=force_new)
            cfg = node.get("config", {}) if isinstance(node, dict) else {}
            child_nodes = cfg.get("nodes") if isinstance(cfg, dict) else None
            if isinstance(child_nodes, list):
                self.ensure_node_tree_identity(child_nodes, force_new=force_new)

    def refresh_node_table_access(self, node):
        if isinstance(node, dict) and (
            not isinstance(node.get("table_access"), dict)
            or bool(node.get("table_access", {}).get("auto_generated", True))
        ):
            node["table_access"] = self.default_table_access_for_node(node)
        return node

    def refresh_node_tree_table_access(self, nodes):
        for node in nodes or []:
            self.ensure_node_identity(node)
            self.refresh_node_table_access(node)
            cfg = node.get("config", {}) if isinstance(node, dict) else {}
            child_nodes = cfg.get("nodes") if isinstance(cfg, dict) else None
            if isinstance(child_nodes, list):
                self.refresh_node_tree_table_access(child_nodes)

    def table_access_permission_items(self):
        return [
            ("read_table", "读表"),
            ("write_table", "写表"),
            ("create_table", "新建表"),
            ("append_rows", "追加行"),
            ("update_rows", "更新行"),
            ("clear_table", "清空表"),
            ("replace_table", "替换表"),
            ("alter_schema", "改结构"),
            ("delete_rows", "删行"),
            ("drop_table", "删表"),
        ]

    def field_permission_items(self):
        return [
            ("read_field", "可读"),
            ("write_field", "可写"),
            ("create_field", "可创建"),
            ("protect_field", "保护"),
        ]

    def get_node_table_access(self, node):
        self.ensure_node_identity(node)
        access = node.get("table_access")
        if not isinstance(access, dict):
            access = self.default_table_access_for_node(node)
            node["table_access"] = access
        access.setdefault("version", 1)
        tables = access.get("tables")
        if not isinstance(tables, list):
            access["tables"] = []
        return access

    def mark_node_table_access_manual(self, node):
        access = self.get_node_table_access(node)
        access["auto_generated"] = False
        return access

    def table_access_table_choices(self, node=None):
        values = ["__CURRENT_TABLE__"]
        try:
            values.extend(self.app.get_table_names())
        except Exception:
            pass
        if isinstance(node, dict):
            for entry in self.get_node_table_access(node).get("tables", []):
                table = str((entry or {}).get("table", "") or "").strip()
                if table:
                    values.append(table)
        result = []
        for value in values:
            if value not in result:
                result.append(value)
        return result

    def table_permission_summary(self, entry):
        perms = (entry or {}).get("permissions") or {}
        labels = []
        label_map = dict(self.table_access_permission_items())
        for key, _ in self.table_access_permission_items():
            if perms.get(key):
                labels.append(label_map.get(key, key))
        if not labels:
            return "无权限"
        return "/".join(labels[:4]) + ("..." if len(labels) > 4 else "")

    def table_access_entry_table_label(self, entry):
        return workflow_table_access_entry_table_label(entry)

    def table_access_operation_summary(self, entry):
        return workflow_table_access_operation_summary(
            entry,
            write_mode_formatter=self.write_mode_display_text,
        )

    def table_access_entry_status(self, entry):
        return workflow_table_access_entry_status(entry)

    def table_access_node_status(self, node):
        access = self.get_node_table_access(node)
        tables = access.get("tables", [])
        if not tables:
            return "未配置"
        statuses = [self.table_access_entry_status(entry) for entry in tables]
        if any(s in ("未绑定", "未授权") for s in statuses):
            return "待配置"
        if any(s == "危险写入" for s in statuses):
            return "需确认"
        if any(s == "已授权" for s in statuses):
            return "已授权"
        if all(s in ("只读", "只记录", "当前表") for s in statuses):
            return "只读/记录"
        return "OK"

    def table_access_field_items(self, entry):
        return workflow_table_access_field_items(entry)

    def find_table_access_field_rule(self, entry, target="", source="", field_index=None):
        return workflow_find_table_access_field_rule(entry, target=target, source=source, field_index=field_index)

    def make_table_access_field_key(self, mapping, source_field, target_field):
        return workflow_make_table_access_field_key(mapping, source_field, target_field)

    def field_permission_status(self, item):
        item = item or {}
        perms = item.get("permissions") or {}
        if perms.get("protect_field"):
            return "保护"
        if perms.get("write_field"):
            return "可写"
        if perms.get("read_field"):
            return "只读"
        return "未授权"

    def field_bool_text(self, value):
        return "是" if bool(value) else "否"

    def get_table_access_field_choices(self, node_index, entry):
        entry = entry or {}
        table = str(entry.get("table", "") or "").strip()
        choices = []
        try:
            headers, _ = self.get_headers_rows_before(node_index)
            choices.extend(headers or [])
        except Exception:
            choices.extend(self.preview_headers or [])
        if table and table != "__CURRENT_TABLE__" and entry.get("source_type", "SQLite表") == "SQLite表":
            try:
                choices.extend(self.app.get_table_columns(table))
            except Exception:
                pass
        for _, item in self.table_access_field_items(entry):
            for key in ("source_field", "target_field", "field", "name"):
                value = str(item.get(key, "") or "").strip()
                if value:
                    choices.append(value)
        result = []
        for value in choices:
            if value and value not in result:
                result.append(value)
        return result

    def auto_match_table_access_fields(self, node_index, entry):
        entry = entry or {}
        source_fields = []
        try:
            source_fields, _ = self.get_headers_rows_before(node_index)
        except Exception:
            source_fields = list(self.preview_headers or [])

        table = str(entry.get("table", "") or "").strip()
        target_fields = []
        if table and table != "__CURRENT_TABLE__" and entry.get("source_type", "SQLite表") == "SQLite表":
            try:
                target_fields = self.app.get_table_columns(table)
            except Exception:
                target_fields = []
        return workflow_apply_auto_field_mapping_by_name(
            entry,
            source_fields,
            target_fields,
            lambda value: self.app.sanitize_sql_name(value, ""),
            make_key=self.make_table_access_field_key,
        )

    def auto_match_table_access_fields_by_order(self, node_index, entry):
        entry = entry or {}
        try:
            source_fields, _ = self.get_headers_rows_before(node_index)
        except Exception:
            source_fields = list(self.preview_headers or [])

        table = str(entry.get("table", "") or "").strip()
        target_fields = []
        if table and table != "__CURRENT_TABLE__" and entry.get("source_type", "SQLite表") == "SQLite表":
            try:
                target_fields = self.app.get_table_columns(table)
            except Exception:
                target_fields = []
        return workflow_apply_auto_field_mapping_by_order(entry, source_fields, target_fields)

    def apply_table_access_preset_to_vars(self, preset, permission_vars, log_only_var=None):
        config = workflow_table_access_preset_config(
            preset,
            [key for key, _ in self.table_access_permission_items()],
        )
        if config is None:
            return
        for key, var in permission_vars.items():
            var.set(bool(config["permissions"].get(key)))
        if log_only_var is not None:
            log_only_var.set(bool(config["log_only"]))

    def table_access_entry_match_score(self, actual, expected):
        return workflow_table_access_entry_match_score(actual, expected)

    def find_matching_table_access_entry(self, actual_tables, expected):
        return workflow_find_matching_table_access_entry(actual_tables, expected)

    def normalize_precheck_transit_name(self, table_name):
        return workflow_normalize_precheck_transit_name(table_name)

    def add_table_access_precheck_issue(self, issues, severity, node_label, node, entry, message,
                                        suggestion="", category="permission", blocking=None):
        issues.append(workflow_make_table_access_precheck_issue(
            severity,
            node_label,
            node,
            entry,
            message,
            suggestion=suggestion,
            category=category,
            blocking=blocking,
            write_mode_formatter=self.write_mode_display_text,
        ))

    def table_access_precheck_summary_text(self, issues):
        return workflow_table_access_precheck_summary_text(issues)

    def table_access_precheck_actionable(self, issues):
        return workflow_table_access_precheck_actionable(issues)

    def table_access_precheck_blocking(self, issues):
        return workflow_table_access_precheck_blocking(issues)

    def get_precheck_sqlite_tables(self):
        db_path = self.get_workflow_db_path()
        if not db_path or not os.path.exists(db_path):
            return None
        try:
            return set(TableAccessManager(db_path, node_type="权限预检").list_tables())
        except Exception:
            return None

    def confirm_table_access_precheck(self, execute_actions=True, stop_index=None):
        issues = self.build_table_access_precheck(execute_actions=execute_actions, stop_index=stop_index)
        self.last_table_access_precheck = list(issues or [])
        actionable = self.table_access_precheck_actionable(issues)
        if not actionable:
            self.status_var.set(self.table_access_precheck_summary_text(issues))
            return True
        policy = self.normalize_table_access_policy()
        if policy == "audit":
            self.status_var.set(self.table_access_precheck_summary_text(actionable) + " 当前策略为只审计，执行不会因预检提示而中断。")
            return True
        if policy == "strict":
            blocking = self.table_access_precheck_blocking(actionable)
            if not blocking:
                self.status_var.set(self.table_access_precheck_summary_text(actionable) + " 当前仅有风险提醒，强制模式允许继续执行。")
                return True
            self.show_table_access_precheck_dialog(
                blocking,
                title="执行前权限预检 - 强制拦截",
                allow_continue=False,
            )
            self.status_var.set("执行计划已拦截：当前权限策略为强制拦截，请先处理权限预检项。")
            return False
        return self.show_table_access_precheck_dialog(
            actionable,
            title="执行前权限预检",
            allow_continue=True,
        )

    def center_toplevel(self, win, parent=None, width=None, height=None):
        """把 Toplevel 放到父窗口中心；没有父窗口时放到屏幕中心。"""
        try:
            parent = parent or self.window
            win.update_idletasks()
            w = int(width or win.winfo_width() or win.winfo_reqwidth() or 600)
            h = int(height or win.winfo_height() or win.winfo_reqheight() or 400)
            if parent is not None and parent.winfo_exists():
                parent.update_idletasks()
                px = parent.winfo_rootx()
                py = parent.winfo_rooty()
                pw = parent.winfo_width()
                ph = parent.winfo_height()
                if pw <= 1 or ph <= 1:
                    px = py = 0
                    pw = win.winfo_screenwidth()
                    ph = win.winfo_screenheight()
            else:
                px = py = 0
                pw = win.winfo_screenwidth()
                ph = win.winfo_screenheight()
            x = max(0, px + (pw - w) // 2)
            y = max(0, py + (ph - h) // 2)
            win.geometry(f"{w}x{h}+{x}+{y}" if width or height else f"+{x}+{y}")
        except Exception:
            pass

    def show_centered_toplevel(self, win, parent=None, width=None, height=None):
        self.center_toplevel(win, parent, width, height)
        try:
            win.deiconify()
        except Exception:
            pass
        try:
            win.lift()
        except Exception:
            pass
        try:
            win.focus_set()
        except Exception:
            pass

    def default_config_for_type(self, node_type):
        table_names = []
        needs_sqlite_defaults = {"匹配值输出列名", "选定列写入指定表", "字段映射写入表"}
        if node_type in needs_sqlite_defaults:
            try:
                table_names = self.app.get_table_names()
            except Exception:
                pass
        table_columns = {}
        for table in table_names[:1]:
            try:
                table_columns[table] = self.app.get_table_columns(table)
            except Exception:
                table_columns[table] = []
        return workflow_default_config_for_type(
            node_type,
            preview_headers=self.preview_headers,
            table_names=table_names,
            table_columns=table_columns,
            app_dir=getattr(self.app, "app_dir", get_app_dir()),
        )

    def default_name_for_node(self, node_type):
        return {
            "节点组 / 子工作流": "节点组 / 子工作流",
            "循环执行起点": "循环执行起点",
            "循环判断回跳": "循环判断回跳",
            "批量替换": "批量替换",
            "数据提取": "数据提取",
            "格式规范化 / 日期时间解析": "格式规范化 / 日期时间解析",
            "新建日期时间列": "新建日期时间列",
            "新建列": "新建列",
            "合并列": "合并列",
            "批量更改列名": "批量更改列名",
            "去重 / 重复数据处理": "去重 / 重复数据处理",
            "列数字运算": "列数字运算",
            "匹配值输出列名": "匹配值输出列名",
            "复制列": "复制列",
            "复制行": "复制行",
            "删除行": "删除行",
            "填充值": "填充值",
            "序列填充": "序列填充",
            "区域填充": "区域填充",
            "行数据映射填充": "行数据映射填充",
            "保存中转数据": "保存中转数据",
            "字段映射写入表": "字段映射写入表",
            "高级筛选": "筛选数据",
            "删除列": "删除列",
            "移动列": "整理列顺序",
        }.get(node_type, node_type)

    def add_node(self):
        node_type = self.node_type_var.get()
        if node_type in getattr(self, "plugin_display_map", {}):
            plugin_id = self.plugin_display_map[node_type]
            plugin_info = self.plugin_registry.get(plugin_id, {}).get("info", {})
            node = {
                "enabled": True,
                "type": "插件节点",
                "name": plugin_info.get("name", plugin_id),
                "config": self.default_config_for_plugin(plugin_id),
            }
        else:
            node = {
                "enabled": True,
                "type": node_type,
                "name": self.default_name_for_node(node_type),
                "config": self.default_config_for_type(node_type),
            }
        self.ensure_node_identity(node)
        selected = self.node_listbox.curselection()
        insert_at = int(selected[0]) + 1 if len(selected) == 1 else len(self.nodes)
        self.nodes.insert(insert_at, node)
        self.refresh_node_list(select_index=insert_at, reveal=True)
        self.build_node_config(insert_at)
        if len(selected) == 1:
            self.status_var.set(f"已在当前节点下方插入：{node.get('name', node.get('type', '节点'))}")
        else:
            self.status_var.set(f"已追加节点：{node.get('name', node.get('type', '节点'))}")

    def delete_node(self):
        idx = self.get_selected_node_index()
        if idx is None:
            return
        del self.nodes[idx]
        self.refresh_node_list()
        self.rebuild_current_config()

    def move_node_up(self):
        idx = self.get_selected_node_index()
        if idx is None or idx <= 0:
            return
        self.nodes[idx - 1], self.nodes[idx] = self.nodes[idx], self.nodes[idx - 1]
        self.refresh_node_list(select_index=idx - 1, reveal=True)
        self.rebuild_current_config()

    def move_node_down(self):
        idx = self.get_selected_node_index()
        if idx is None or idx >= len(self.nodes) - 1:
            return
        self.nodes[idx + 1], self.nodes[idx] = self.nodes[idx], self.nodes[idx + 1]
        self.refresh_node_list(select_index=idx + 1, reveal=True)
        self.rebuild_current_config()

    def toggle_node_enabled(self):
        idx = self.get_selected_node_index()
        if idx is None:
            return
        self.nodes[idx]["enabled"] = not self.nodes[idx].get("enabled", True)
        self.refresh_node_list(select_index=idx, reveal=True)

    def copy_node(self):
        idx = self.get_selected_node_index()
        if idx is None:
            return
        import copy
        new_node = copy.deepcopy(self.nodes[idx])
        new_node["name"] = f"{new_node.get('name', new_node.get('type'))}_复制"
        self.ensure_node_tree_identity([new_node], force_new=True)
        self.nodes.insert(idx + 1, new_node)
        self.refresh_node_list(select_index=idx + 1, reveal=True)
        self.rebuild_current_config()

    def clear_nodes(self):
        if self.nodes and not messagebox.askyesno("确认", "是否清空所有计划节点？"):
            return
        self.nodes.clear()
        self.refresh_node_list()
        self.show_empty_config()

    def update_node_name(self, idx, name_var):
        if 0 <= idx < len(self.nodes):
            self.nodes[idx]["name"] = name_var.get().strip() or self.nodes[idx]["type"]
            self.refresh_node_list(select_index=idx, reveal=True)

    def make_config_preview_context(self):
        """
        配置界面专用的预运行上下文。

        用途：刷新某个节点配置时，会临时运行它前面的节点，以便拿到“到当前节点为止”的字段列表和中转副表。
        这里允许“选定列写入指定表”在配置预运行时写入【当前工作表】和【中转副表】，
        这样后续高级筛选、匹配值输出列名、插件节点等配置界面才能看到这些临时字段。

        注意：selected_columns_config_preview_only 会在该节点内部拦截 SQLite 写入，
        防止只是切换/刷新配置界面时误改真实数据库。
        """
        return {
            "transit_tables": {},
            "loop_states": {},
            "loop_results": {},
            "is_config_probe": True,
            "allow_selected_columns_write_in_preview": True,
            "selected_columns_config_preview_only": True,
        }

    def get_headers_rows_before(self, idx):
        return self.run_plan(
            stop_index=idx - 1,
            raise_error=True,
            initial_context=self.make_config_preview_context(),
        )[:2]

    def get_transit_context_before(self, idx):
        """运行到指定节点之前，取得已经保存的内存中转副表。配置界面用于列出可引用的中转表。"""
        if idx is None or idx <= 0:
            return self.make_config_preview_context()
        try:
            _, _, _, context = self.run_plan(
                stop_index=idx - 1,
                raise_error=False,
                return_context=True,
                initial_context=self.make_config_preview_context(),
            )
            return context
        except Exception:
            return self.make_config_preview_context()

    def make_node_enabled_var(self, idx):
        var = tk.BooleanVar(value=self.nodes[idx].get("enabled", True))
        def on_change(*_):
            if 0 <= idx < len(self.nodes):
                self.nodes[idx]["enabled"] = bool(var.get())
                self.refresh_node_list(select_index=idx, reveal=True)
        var.trace_add("write", on_change)
        return var

    def add_labeled_entry(self, parent, label, value, row, col, width=20):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky=tk.W, padx=4, pady=4)
        var = tk.StringVar(value=value)
        ttk.Entry(parent, textvariable=var, width=width).grid(row=row, column=col + 1, sticky=tk.W, padx=4, pady=4)
        return var

    def add_labeled_combo(self, parent, label, value, values, row, col, width=20, readonly=True):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky=tk.W, padx=4, pady=4)
        var = tk.StringVar(value=value if value in values or not readonly else (values[0] if values else value))
        state = "readonly" if readonly else "normal"
        ttk.Combobox(parent, textvariable=var, values=values, width=width, state=state).grid(row=row, column=col + 1, sticky=tk.W, padx=4, pady=4)
        return var

    def add_labeled_combo_control(self, parent, label, value, values, row, col, width=20, readonly=True):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky=tk.W, padx=4, pady=4)
        var = tk.StringVar(value=value if value in values or not readonly else (values[0] if values else value))
        state = "readonly" if readonly else "normal"
        combo = ttk.Combobox(parent, textvariable=var, values=values, width=width, state=state)
        combo.grid(row=row, column=col + 1, sticky=tk.W, padx=4, pady=4)
        return var, combo

    def refresh_combo_values(self, combo, var, values, keep_custom=True, fallback=""):
        values = [str(v) for v in (values or [])]
        current = str(var.get() or "")
        display_values = list(values)
        if current and current not in display_values and keep_custom:
            display_values = [current] + display_values
        combo.configure(values=display_values)
        if not current:
            var.set(fallback if fallback in values else (values[0] if values else fallback))
        elif current not in values and not keep_custom:
            var.set(fallback if fallback in values else (values[0] if values else fallback))

    def refresh_listbox_values(self, listbox, values, selected_values=None):
        selected_values = set(selected_values or [])
        listbox.delete(0, tk.END)
        selected_indices = []
        for i, value in enumerate(values or []):
            listbox.insert(tk.END, value)
            if value in selected_values:
                selected_indices.append(i)
        for i in selected_indices:
            listbox.selection_set(i)
        return selected_indices

    def sync_var_to_config(self, var, config, key, cast=str):
        def on_change(*_):
            try:
                config[key] = cast(var.get())
            except Exception:
                config[key] = var.get()
        var.trace_add("write", on_change)
        return var

    def sync_bool_to_config(self, var, config, key):
        def on_change(*_):
            config[key] = bool(var.get())
        var.trace_add("write", on_change)
        return var


    # ------------------------------
    # 节点组 / 子工作流
    # ------------------------------
    def merge_selected_nodes_to_group(self):
        return workflow_group_template_ui.merge_selected_nodes_to_group(
            self,
            messagebox_module=messagebox,
            simpledialog_module=simpledialog,
        )

    def expand_selected_group(self):
        return workflow_group_template_ui.expand_selected_group(self, messagebox_module=messagebox)

    def get_group_dir(self):
        return workflow_group_template_ui.get_group_dir(self, get_app_dir)

    def validate_group_template_data(self, data):
        return workflow_group_template_ui.validate_group_template_data(data)

    def build_group_template_data(self, config, group_name=None):
        return workflow_group_template_ui.build_group_template_data(config, group_name=group_name)

    def group_config_from_template_data(self, data):
        return workflow_group_template_ui.group_config_from_template_data(data)

    def save_group_template_from_config(self, config):
        return workflow_group_template_ui.save_group_template_from_config(
            self,
            config,
            atomic_write_json,
            messagebox_module=messagebox,
            filedialog_module=filedialog,
        )

    def load_group_template_dialog(self):
        return workflow_group_template_ui.load_group_template_dialog(
            self,
            load_json_file_with_recovery,
            messagebox_module=messagebox,
            filedialog_module=filedialog,
        )

    def open_group_dir(self):
        return workflow_group_template_ui.open_group_dir(self, messagebox_module=messagebox)

    def loop_last_non_empty_row_index(self, headers, rows, field):
        return workflow_loop_last_non_empty_row_index(headers, rows, field)

    def evaluate_loop_condition(self, headers, rows, config, context=None, loop_state=None):
        return workflow_evaluate_loop_condition(headers, rows, config, loop_state=loop_state)

    def find_loop_start_index(self, loop_id, current_idx, nodes=None):
        node_list = nodes if nodes is not None else self.nodes
        return workflow_find_loop_start_index(loop_id, current_idx, node_list)

    def find_loop_judge_index(self, loop_id, start_idx, end_idx, nodes=None):
        node_list = nodes if nodes is not None else self.nodes
        return workflow_find_loop_judge_index(loop_id, start_idx, end_idx, node_list)

    def format_logs(self, logs):
        if not logs:
            return ""
        last = logs[-3:]
        text = "  最近节点：" + "；".join(last)
        return text[:500]

    def parse_group_input_fields(self, config):
        return workflow_parse_group_input_fields(config)


    def parse_new_column_names_for_group_analysis(self, text, strip_name=True, allow_empty=False):
        return workflow_group_field_analysis.parse_new_column_names_for_group_analysis(
            text,
            strip_name=strip_name,
            allow_empty=allow_empty,
        )

    def add_group_field_ref(self, target, value):
        return workflow_group_field_analysis.add_group_field_ref(target, value)

    def add_group_field_refs_from_dict_list(self, target, items, keys):
        return workflow_group_field_analysis.add_group_field_refs_from_dict_list(target, items, keys)

    def classify_group_filter_field_reference(self, field, extra_tables=None):
        return workflow_group_field_analysis.classify_group_filter_field_reference(
            field,
            extra_tables=extra_tables,
        )

    def get_group_filter_external_output_fields(self, config, context=None):
        return workflow_group_field_analysis.get_group_filter_external_output_fields(
            self,
            config,
            context=context,
        )

    def analyze_group_filter_field_io(self, config, context=None):
        return workflow_group_field_analysis.analyze_group_filter_field_io(
            self,
            config,
            context=context,
        )

    def analyze_group_inner_node_field_io(self, node, context=None):
        return workflow_group_field_analysis.analyze_group_inner_node_field_io(
            self,
            node,
            context=context,
        )

    def collect_group_fields_from_nested_config(self, target, value, field_keys=None):
        return workflow_group_field_analysis.collect_group_fields_from_nested_config(
            target,
            value,
            field_keys=field_keys,
        )

    def infer_group_input_fields_from_nodes(self, nodes, context=None):
        return workflow_group_field_analysis.infer_group_input_fields_from_nodes(
            self,
            nodes,
            context=context,
        )

    def format_group_input_infer_details(self, inferred, details, limit=20):
        return workflow_group_field_analysis.format_group_input_infer_details(
            inferred,
            details,
            limit=limit,
        )

    def normalize_group_transit_conflict_mode(self, mode):
        return workflow_normalize_group_transit_conflict_mode(mode)

    def normalize_group_sqlite_mode(self, mode):
        return workflow_normalize_group_sqlite_mode(mode)

    def build_group_input_table(self, source_headers, source_rows, config):
        return workflow_build_group_input_table(source_headers, source_rows, config)

    def make_group_child_context(self, parent_context, config):
        return workflow_make_group_child_context(parent_context, config)

    def field_index(self, headers, field):
        if field not in headers:
            raise ValueError(f"字段不存在：{field}")
        return headers.index(field)

    def safe_cell(self, row, idx):
        return core_safe_cell(row, idx)

    def normalize_rows(self, rows, col_count):
        return core_normalize_rows(rows, col_count)

    def compare_values(self, text, op, value, case_sensitive=True):
        text = "" if text is None else str(text)
        value = "" if value is None else str(value)
        t = text if case_sensitive else text.lower()
        v = value if case_sensitive else value.lower()
        if op == "等于" or op == "完全相等":
            return t == v
        if op == "不等于":
            return t != v
        if op == "包含":
            return v in t
        if op == "不包含":
            return v not in t
        if op == "开头是":
            return t.startswith(v)
        if op == "结尾是":
            return t.endswith(v)
        if op == "为空":
            return text == ""
        if op == "不为空":
            return text != ""
        if op == "正则匹配":
            flags = 0 if case_sensitive else re.IGNORECASE
            return re.search(value, text, flags) is not None
        if op in ["大于", "小于", "大于等于", "小于等于"]:
            try:
                a = float(text)
                b = float(value)
            except Exception:
                return False
            if op == "大于":
                return a > b
            if op == "小于":
                return a < b
            if op == "大于等于":
                return a >= b
            if op == "小于等于":
                return a <= b
        return False

    def parse_extensions_filter(self, text_value):
        return workflow_parse_extensions_filter(text_value)

    def is_hidden_path(self, path):
        return workflow_is_hidden_path(path)

    def check_workflow_cancelled(self, context=None):
        """长循环节点内部调用：用户点击取消后，在安全检查点停止。"""
        cancel_event = (context or {}).get("cancel_event")
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("用户取消后台执行")

    def check_workflow_cancelled_periodically(self, context, index, interval=500):
        if index == 0 or index % max(1, int(interval)) == 0:
            self.check_workflow_cancelled(context)

    def report_workflow_node_progress(self, context=None, current=None, total=None, message="", node_name=""):
        """长循环节点内部调用：通过后台 Queue 回传节点内行级/项目级进度。"""
        callback = (context or {}).get("progress_callback")
        if not callable(callback):
            return
        try:
            callback({
                "type": "node_progress",
                "node_name": node_name or "当前节点",
                "current": current,
                "total": total,
                "message": message or "处理中",
            })
        except Exception:
            pass

    def get_or_add_column_index(self, headers, rows, column_name):
        column_name = str(column_name or "").strip()
        if not column_name:
            column_name = "结果"
        if column_name in headers:
            return headers.index(column_name), headers, rows
        headers = list(headers)
        rows = [list(row) for row in rows]
        headers.append(column_name)
        for row in rows:
            row.append("")
        return len(headers) - 1, headers, rows

    def parse_int(self, value, name):
        return workflow_parse_int(value, name)

    def safe_int(self, value, default=0):
        try:
            return int(str(value).strip())
        except Exception:
            return default

    def apply_unmatched_extract(self, text, status, config):
        return workflow_apply_unmatched_extract(text, status, config)

    def post_extract_result(self, result, config):
        return workflow_post_extract_result(result, config)

    def extract_one_value(self, original, config):
        return workflow_extract_one_value(original, config)

    def get_unique_header(self, base_name, headers):
        name = str(base_name or "新字段").strip() or "新字段"
        if name not in headers:
            return name
        counter = 2
        while f"{name}_{counter}" in headers:
            counter += 1
        return f"{name}_{counter}"

    def normalize_datetime_source_text(self, value):
        return workflow_normalize_datetime_source_text(value)

    def parse_format_int(self, value, name, allow_zero=False):
        return workflow_parse_format_int(value, name, allow_zero=allow_zero)

    def slice_by_position(self, text, start, length, base, name):
        return workflow_slice_by_position(text, start, length, base, name)

    def complete_format_year(self, value, config):
        return workflow_complete_format_year(value, config)

    def build_date_parts(self, year, month, day, config):
        return workflow_build_date_parts(year, month, day, config)

    def build_time_parts(self, hour, minute="0", second="0"):
        return workflow_build_time_parts(hour, minute, second)

    def parse_date_fixed(self, text, config):
        return workflow_parse_date_fixed(text, config)

    def parse_time_fixed(self, text, config):
        return workflow_parse_time_fixed(text, config)

    def split_by_config_delimiter(self, text, kind, config):
        return workflow_split_by_config_delimiter(text, kind, config)

    def parse_date_delimited(self, text, config):
        return workflow_parse_date_delimited(text, config)

    def parse_time_delimited(self, text, config):
        return workflow_parse_time_delimited(text, config)

    def parse_date_auto_common(self, text, config):
        return workflow_parse_date_auto_common(text, config)

    def parse_time_auto_common(self, text, config):
        return workflow_parse_time_auto_common(text, config)

    def parse_format_datetime_value(self, date_text, time_text, config):
        return workflow_parse_format_datetime_value(date_text, time_text, config)

    def render_format_template(self, parts, template):
        return workflow_render_format_template(parts, template)

    def format_output_value(self, parts, config):
        return workflow_format_output_value(parts, config)

    def apply_unmatched_format_value(self, original, status, config):
        return workflow_apply_unmatched_format_value(original, status, config)

    def build_format_component_columns(self, parts, parse_type, prefix):
        return workflow_build_format_component_columns(parts, parse_type, prefix)

    def get_datetime_parse_warning(self, original, config, parts):
        return workflow_get_datetime_parse_warning(original, config, parts)

    def render_current_datetime_template(self, dt, config):
        return workflow_render_current_datetime_template(dt, config)

    def parse_new_columns_specs(self, config):
        return workflow_parse_new_columns_specs(config)

    def ensure_field_exists(self, headers, rows, field_name):
        return workflow_ensure_field_exists(headers, rows, field_name)

    def ensure_row_count(self, rows, row_count, col_count):
        return workflow_ensure_row_count(
            rows,
            row_count,
            col_count,
            max_expanded_rows=self.MAX_EXPANDED_ROWS,
        )

    def ensure_target_cell_limit(self, row_count, col_count):
        return workflow_ensure_target_cell_limit(
            row_count,
            col_count,
            max_target_cells=self.MAX_TARGET_CELLS,
        )

    def ensure_column_count(self, headers, rows, col_count, base_name="区域复制列"):
        return workflow_ensure_column_count(headers, rows, col_count, base_name)

    def parse_row_number(self, value, name="行号"):
        n = self.parse_int(value, name)
        if n < 1:
            raise ValueError(f"{name} 必须大于等于 1。")
        return n

    def get_config_cell_value(self, headers, rows, config, target_row_idx=None):
        return workflow_get_config_cell_value(headers, rows, config, target_row_idx=target_row_idx)

    def resolve_start_row_index_by_mode(self, headers, rows, target_field, config):
        return workflow_resolve_start_row_index_by_mode(headers, rows, target_field, config)

    def get_source_column_values_by_config(self, headers, rows, config):
        return workflow_get_source_column_values_by_config(headers, rows, config)

    def get_cycle_source_values_by_config(self, headers, rows, config, multi_field=False):
        return workflow_get_cycle_source_values_by_config(headers, rows, config, multi_field=multi_field)

    def get_source_row_multi_field_values_by_config(self, headers, rows, config):
        return workflow_get_source_row_multi_field_values_by_config(headers, rows, config)

    def get_source_area_values_by_config(self, headers, rows, config):
        return workflow_get_source_area_values_by_config(headers, rows, config)

    def resolve_sequence_count_by_source(self, headers, rows, config):
        return workflow_resolve_sequence_count_by_source(headers, rows, config)

    def row_is_empty(self, row, col_count):
        return workflow_row_is_empty(row, col_count)

    def last_non_empty_row_index_by_field(self, headers, rows, field_name):
        return workflow_last_non_empty_row_index_by_field(headers, rows, field_name)

    def resolve_area_end_row_index(self, headers, rows, config):
        return workflow_resolve_area_end_row_index(headers, rows, config)

    def get_fill_targets(self, headers, rows, target_field, start_row_value, direction, end_mode, count_value, end_row_value, end_field_value, reference_field_value="", allow_expand_rows=True, allow_expand_cols=False):
        return workflow_get_fill_targets(
            headers,
            rows,
            target_field,
            start_row_value,
            direction,
            end_mode,
            count_value,
            end_row_value,
            end_field_value,
            reference_field_value=reference_field_value,
            allow_expand_rows=allow_expand_rows,
            allow_expand_cols=allow_expand_cols,
            max_expanded_rows=self.MAX_EXPANDED_ROWS,
            max_target_cells=self.MAX_TARGET_CELLS,
        )

    def should_write_cell(self, current_value, overwrite_rule):
        return workflow_should_write_cell(current_value, overwrite_rule)

    def format_sequence_value(self, value, config):
        return workflow_format_sequence_value(value, config)

    def get_positive_int(self, value, default_value):
        try:
            n = int(str(value).strip())
            return n if n > 0 else default_value
        except Exception:
            return default_value

    def get_plan_filter_available_fields(self, headers, extra_tables, context=None):
        fields = [f"当前表.{h}" for h in headers]
        transit_tables = (context or {}).get("transit_tables", {})
        for table in extra_tables:
            try:
                if str(table).startswith("中转:"):
                    name = str(table).split(":", 1)[1]
                    item = transit_tables.get(name, {})
                    for col in item.get("headers", []):
                        fields.append(f"{table}.{col}")
                else:
                    for col in self.get_workflow_sqlite_columns(table, context):
                        fields.append(f"{table}.{col}")
            except Exception:
                continue
        return fields

    def normalize_plan_filter_field_reference(self, field, headers, extra_tables=None):
        return workflow_normalize_plan_filter_field_reference(field, headers, extra_tables)

    def normalize_plan_filter_config_field_references(self, config, headers, extra_tables=None):
        return workflow_normalize_plan_filter_config_field_references(config, headers, extra_tables)

    def get_plan_filter_output_base_headers(self, lookup_fields, headers):
        return workflow_get_plan_filter_output_base_headers(lookup_fields, headers)

    def get_plan_filter_output_headers(self, lookup_fields, headers):
        return workflow_get_plan_filter_output_headers(lookup_fields, headers)

    def get_plan_filter_output_header_conflicts(self, lookup_fields, headers):
        return workflow_get_plan_filter_output_header_conflicts(lookup_fields, headers)

    def plan_filter_field_belongs_to_table(self, field, table_name):
        return workflow_plan_filter_field_belongs_to_table(field, table_name)

    def get_plan_filter_field_owner(self, field, headers, extra_tables):
        return workflow_get_plan_filter_field_owner(field, headers, extra_tables)

    def get_plan_filter_hash_join_availability(self, headers, extra_tables, join_rules, join_logic):
        return workflow_get_plan_filter_hash_join_availability(headers, extra_tables, join_rules, join_logic)

    def get_plan_filter_config_warnings(self, headers, extra_tables, conditions, join_rules, join_logic):
        return workflow_get_plan_filter_config_warnings(headers, extra_tables, conditions, join_rules, join_logic)

    def add_plan_filter_required_field(self, field, headers, extra_tables, current_headers, table_fields):
        return workflow_add_plan_filter_required_field(field, headers, extra_tables, current_headers, table_fields)

    def collect_plan_filter_required_fields(self, headers, extra_tables, conditions, join_rules, output_fields, final_fields):
        return workflow_collect_plan_filter_required_fields(
            headers, extra_tables, conditions, join_rules, output_fields, final_fields
        )

    def get_required_columns_for_plan_table(self, table_name, columns, required_fields):
        return workflow_get_required_columns_for_plan_table(table_name, columns, required_fields)

    def make_current_table_records(self, headers, rows, required_headers=None):
        return workflow_make_current_table_records(headers, rows, required_headers)

    def normalize_filter_condition_value_source(self, cond):
        return workflow_normalize_filter_condition_value_source(cond)

    def resolve_plan_condition_value(self, record, cond):
        return workflow_resolve_plan_condition_value(record, cond)

    def eval_plan_condition_record(self, record, cond):
        return workflow_eval_plan_condition_record(record, cond)

    def eval_plan_join_rule_record(self, record, rule):
        return workflow_eval_plan_join_rule_record(record, rule)

    def record_passes_plan_conditions(self, record, conditions, logic):
        return workflow_record_passes_plan_conditions(record, conditions, logic)

    def plan_filter_condition_dependencies(self, cond):
        return workflow_plan_filter_condition_dependencies(cond)

    def record_survives_available_plan_conditions(self, record, conditions, logic):
        return workflow_record_survives_available_plan_conditions(record, conditions, logic)

    def record_passes_plan_join_rules(self, record, join_rules, logic="AND"):
        return workflow_record_passes_plan_join_rules(record, join_rules, logic)

    def get_plan_filter_hash_join_rules(self, table_name, join_rules, join_logic, right_records):
        return workflow_get_plan_filter_hash_join_rules(table_name, join_rules, join_logic, right_records)

    def build_plan_filter_right_index(self, right_records, hash_rules):
        return workflow_build_plan_filter_right_index(right_records, hash_rules)

    def iter_plan_filter_join_candidates(self, left_record, right_records, hash_rules, right_index, missing_key_records):
        return workflow_iter_plan_filter_join_candidates(
            left_record, right_records, hash_rules, right_index, missing_key_records
        )


    def get_row_mapping_end_index(self, rows, start_idx, config, col_count):
        return workflow_get_row_mapping_end_index(rows, start_idx, config, col_count)

    def make_unique_transit_name(self, base_name, transit_tables):
        return workflow_make_unique_transit_name(base_name, transit_tables)

    def append_headers_rows(self, old_headers, old_rows, new_headers, new_rows):
        return workflow_append_headers_rows(old_headers, old_rows, new_headers, new_rows)

    def compare_writeback_values(self, left, op, right):
        return workflow_compare_writeback_values(left, op, right)

    def build_writeback_full_structure_rows_for_sqlite(self, headers, rows, config, target_columns):
        return workflow_build_writeback_full_structure_rows_for_sqlite(headers, rows, config, target_columns)

    def match_value_output_column_match(self, source_value, lookup_value, mode):
        return workflow_match_value_output_column_match(source_value, lookup_value, mode)

    def make_unique_plan_headers(self, headers):
        """字段名去重：重复字段自动追加 _2、_3。"""
        result = []
        counts = {}
        for i, h in enumerate(headers, start=1):
            base = str(h).strip() or f"列{i}"
            if base not in counts:
                counts[base] = 1
                result.append(base)
            else:
                counts[base] += 1
                candidate = f"{base}_{counts[base]}"
                while candidate in counts:
                    counts[base] += 1
                    candidate = f"{base}_{counts[base]}"
                counts[candidate] = 1
                result.append(candidate)
        return result


    def parse_numeric_value_for_column_op(self, value):
        return workflow_parse_numeric_value_for_column_op(value)

    def format_numeric_column_result(self, value, config):
        return workflow_format_numeric_column_result(value, config)

    def get_numeric_node_row_indexes(self, headers, rows, config):
        return workflow_get_numeric_node_row_indexes(headers, rows, config)

    def numeric_node_fallback_value(self, original_value, policy, fixed_value, fail_text):
        return workflow_numeric_node_fallback_value(original_value, policy, fixed_value, fail_text)

    def make_unique_headers_for_append(self, existing_headers, new_headers):
        """给追加字段生成不重复字段名。"""
        return core_make_unique_headers_for_append(existing_headers, new_headers)

    def get_plan_dir(self):
        """返回程序真实目录下的 plan 模板目录，并确保目录存在。"""
        base_dir = getattr(self.app, "app_dir", get_app_dir())
        plan_dir = os.path.join(base_dir, "plan")
        os.makedirs(plan_dir, exist_ok=True)
        return plan_dir

    def sanitize_plan_file_name(self, name):
        """生成适合作为文件名的计划模板名称。"""
        name = str(name or "工作流计划").strip()
        name = re.sub(r'[\\/:*?"<>|]+', "_", name)
        name = re.sub(r"\s+", "_", name)
        return name or "工作流计划"

    def build_plan_template_data(self, plan_name=None):
        """
        收集当前计划模板数据。新版模板必须带 template_type。

        plan_name 优先由保存时选择的 JSON 文件名传入，
        这样模板下拉菜单中的计划名会和实际保存文件名保持一致。
        """
        plan_name = str(plan_name or "").strip()
        if not plan_name:
            plan_name = self.output_table_var.get().strip() or "工作流计划"

        self.refresh_node_tree_table_access(self.nodes)
        return {
            "template_type": "workflow_plan",
            "version": "1.0",
            "plan_name": plan_name,
            "nodes": self.nodes,
            "output_mode": self.output_mode_var.get(),
            "output_table": self.output_table_var.get(),
            "backup_before_overwrite": self.backup_before_overwrite_var.get(),
            "table_access_policy": self.normalize_table_access_policy(),
        }

    def validate_plan_template_data(self, data):
        """
        只识别新版计划模板：
        - 必须是 dict
        - template_type 必须等于 workflow_plan
        - nodes 必须是 list
        """
        if not isinstance(data, dict):
            return False, "模板内容不是 JSON 对象。"
        if data.get("template_type") != "workflow_plan":
            return False, "template_type 不是 workflow_plan。"
        if not isinstance(data.get("nodes"), list):
            return False, "nodes 字段不存在或不是列表。"
        return True, ""

    def apply_plan_template_data(self, data, source_path=""):
        """把已验证的计划模板应用到当前计划窗口。"""
        ok, reason = self.validate_plan_template_data(data)
        if not ok:
            raise ValueError(reason)

        self.nodes = data.get("nodes", [])
        self.ensure_node_tree_identity(self.nodes)
        self.output_mode_var.set(data.get("output_mode", "输出到主界面预览区"))
        self.output_table_var.set(data.get("output_table", self.make_default_output_table_name()))
        self.backup_before_overwrite_var.set(bool(data.get("backup_before_overwrite", True)))
        self.set_table_access_policy(data.get("table_access_policy", "audit"))
        self.refresh_node_list()
        self.rebuild_current_config()

        if source_path:
            self.status_var.set(f"计划模板已载入：{source_path}")
        else:
            self.status_var.set("计划模板已载入。")

    def open_plan_dir(self):
        """打开程序真实目录下的 plan 模板目录。"""
        os.makedirs(self.plan_dir, exist_ok=True)
        try:
            if hasattr(os, "startfile"):
                os.startfile(self.plan_dir)
            else:
                messagebox.showinfo("plan目录", self.plan_dir)
        except Exception as e:
            messagebox.showerror("打开失败", f"无法打开 plan 目录：\n{self.plan_dir}\n\n{e}")

    def save_plan_template(self):
        os.makedirs(self.plan_dir, exist_ok=True)
        default_name = self.sanitize_plan_file_name(self.output_table_var.get() or "工作流计划") + ".json"
        path = filedialog.asksaveasfilename(
            title="保存计划模板",
            initialdir=self.plan_dir,
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[("JSON模板", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return

        # 使用用户实际保存的 JSON 文件名作为 plan_name。
        # 例如保存为“PDF批量重命名.json”，则 JSON 内部写入：
        # "plan_name": "PDF批量重命名"。
        saved_file_name = os.path.basename(path)
        saved_plan_name = os.path.splitext(saved_file_name)[0].strip() or "工作流计划"

        data = self.build_plan_template_data(plan_name=saved_plan_name)
        try:
            atomic_write_json(path, data)
            self.status_var.set(f"计划模板已保存：{path}；plan_name 已同步为：{saved_plan_name}")
            self.refresh_plan_template_list(show_status=False)

            # 保存后尽量自动选中刚保存的模板，便于确认和后续快速载入。
            if hasattr(self, "plan_template_combo") and hasattr(self, "plan_template_map"):
                abs_saved_path = os.path.abspath(path)
                for display_name, template_path in self.plan_template_map.items():
                    if os.path.abspath(template_path) == abs_saved_path:
                        self.plan_template_var.set(display_name)
                        break
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def load_plan_template_from_path(self, path):
        if not path:
            return
        if self.nodes:
            ok = messagebox.askyesno(
                "确认载入模板",
                "当前计划已有节点，载入模板会覆盖当前计划。\n是否继续？"
            )
            if not ok:
                return
        try:
            data = load_json_file_with_recovery(path, parent=self.window)
            self.apply_plan_template_data(data, source_path=path)
        except Exception as e:
            messagebox.showerror("载入失败", str(e))

    def load_plan_template(self):
        path = filedialog.askopenfilename(
            title="载入计划模板",
            initialdir=self.plan_dir,
            filetypes=[("JSON模板", "*.json"), ("所有文件", "*.*")]
        )
        if not path:
            return
        self.load_plan_template_from_path(path)

    def load_selected_plan_template(self):
        display = self.plan_template_var.get()
        if not display:
            messagebox.showwarning("提示", "请先从下拉菜单选择一个计划模板。")
            return

        path = self.plan_template_map.get(display)
        if not path:
            self.refresh_plan_template_list(show_status=False)
            path = self.plan_template_map.get(display)

        if not path:
            messagebox.showwarning("提示", "选中的计划模板不存在或已失效，请刷新模板列表。")
            return

        self.load_plan_template_from_path(path)


    # ==================== 后台执行 / 进度条管理 ====================
    def get_workflow_log_dir(self):
        log_dir = os.path.join(getattr(self.app, "app_dir", get_app_dir()), "logs", "workflow")
        os.makedirs(log_dir, exist_ok=True)
        return log_dir

    def write_workflow_error_log(self, mode, message, traceback_text="", logs=None, snapshot=None):
        """后台线程错误日志。只写文件，不直接操作 Tkinter。"""
        try:
            log_dir = self.get_workflow_log_dir()
            path = os.path.join(log_dir, f"workflow_error_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.log")
            snapshot = snapshot or {}
            node_count = len(snapshot.get("nodes", self.nodes) or [])
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"任务模式：{mode}\n")
                f.write(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"节点数量：{node_count}\n")
                if snapshot.get("db_path"):
                    f.write(f"数据库：{snapshot.get('db_path')}\n")
                if snapshot.get("workflow_name"):
                    f.write(f"工作流/输出名：{snapshot.get('workflow_name')}\n")
                f.write(f"错误信息：{message}\n\n")
                if logs:
                    f.write("执行日志：\n")
                    for item in logs:
                        f.write(f"- {item}\n")
                    f.write("\n")
                if traceback_text:
                    f.write("Traceback：\n")
                    f.write(traceback_text)
            return path
        except Exception:
            return ""



if __name__ == "__main__":
    # 预留给后续子进程 Worker / PyInstaller 打包使用。当前版本后台执行采用线程 Worker。
    try:
        import multiprocessing
        multiprocessing.freeze_support()
    except Exception:
        pass
    root = tk.Tk()
    app = ClipboardTableApp(root)
    root.mainloop()
