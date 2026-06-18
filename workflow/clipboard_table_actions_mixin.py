# -*- coding: utf-8 -*-
"""Main clipboard table app action handlers."""

import os
from tkinter import messagebox

from workflow.advanced_filter_window import AdvancedFilterWindow
from workflow.batch_replace_window import BatchReplaceWindow
from workflow.data_extract_window import DataExtractWindow
from workflow.merge_columns_window import MergeColumnsWindow


class ClipboardTableActionsMixin:
    """Button and combobox actions for the main clipboard table window."""

    workflow_window_class = None
    advanced_filter_window_class = AdvancedFilterWindow
    batch_replace_window_class = BatchReplaceWindow
    data_extract_window_class = DataExtractWindow
    merge_columns_window_class = MergeColumnsWindow

    def _warn_no_table_data(self):
        messagebox.showwarning("提示", "当前没有可处理的数据，请先读取剪贴板或加载数据库表。")

    def open_plan_workflow(self):
        if not self.headers:
            self._warn_no_table_data()
            return
        if self.workflow_window_class is None:
            raise RuntimeError("workflow_window_class is not configured")
        self.workflow_window_class(self)

    def open_advanced_filter(self):
        db_path = self.db_path_var.get().strip()
        if not db_path:
            messagebox.showwarning("提示", "请先设置 SQLite 数据库路径。")
            return

        if not os.path.exists(db_path):
            messagebox.showwarning("提示", "当前 SQLite 数据库不存在，请先保存数据或选择已有数据库。")
            return

        self.advanced_filter_window_class(self)

    def open_batch_replace(self):
        if not self.headers:
            self._warn_no_table_data()
            return
        self.batch_replace_window_class(self)

    def open_data_extract(self):
        if not self.headers:
            self._warn_no_table_data()
            return
        self.data_extract_window_class(self)

    def open_merge_columns(self):
        if not self.headers:
            self._warn_no_table_data()
            return
        self.merge_columns_window_class(self)

    def on_table_selected(self, event=None):
        table_name = self.table_name_var.get().strip()
        if not table_name:
            return
        self.load_table_from_sqlite(table_name)
