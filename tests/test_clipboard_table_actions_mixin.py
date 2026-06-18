# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from workflow.clipboard_table_actions_mixin import ClipboardTableActionsMixin


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeWindowClass:
    calls = []

    def __init__(self, app):
        self.__class__.calls.append(app)


class FakeApp(ClipboardTableActionsMixin):
    workflow_window_class = FakeWindowClass
    advanced_filter_window_class = FakeWindowClass
    batch_replace_window_class = FakeWindowClass
    data_extract_window_class = FakeWindowClass
    merge_columns_window_class = FakeWindowClass

    def __init__(self):
        self.headers = []
        self.db_path_var = FakeVar("")
        self.table_name_var = FakeVar("")
        self.loaded_tables = []

    def load_table_from_sqlite(self, table_name):
        self.loaded_tables.append(table_name)


class ClipboardTableActionsMixinTests(unittest.TestCase):
    def setUp(self):
        FakeWindowClass.calls = []

    def test_open_plan_workflow_requires_headers(self):
        app = FakeApp()

        with patch("workflow.clipboard_table_actions_mixin.messagebox.showwarning") as warning:
            app.open_plan_workflow()

        warning.assert_called_once_with("提示", "当前没有可处理的数据，请先读取剪贴板或加载数据库表。")
        self.assertEqual(FakeWindowClass.calls, [])

        app.headers = ["A"]
        app.open_plan_workflow()
        self.assertEqual(FakeWindowClass.calls, [app])

    def test_open_table_transform_windows_require_headers(self):
        app = FakeApp()
        actions = [app.open_batch_replace, app.open_data_extract, app.open_merge_columns]

        with patch("workflow.clipboard_table_actions_mixin.messagebox.showwarning") as warning:
            for action in actions:
                action()

        self.assertEqual(warning.call_count, 3)
        self.assertEqual(FakeWindowClass.calls, [])

        app.headers = ["A"]
        for action in actions:
            action()
        self.assertEqual(FakeWindowClass.calls, [app, app, app])

    def test_open_advanced_filter_validates_database_path(self):
        app = FakeApp()

        with patch("workflow.clipboard_table_actions_mixin.messagebox.showwarning") as warning:
            app.open_advanced_filter()
        warning.assert_called_once_with("提示", "请先设置 SQLite 数据库路径。")

        app.db_path_var.set("missing.db")
        with patch("workflow.clipboard_table_actions_mixin.os.path.exists", return_value=False):
            with patch("workflow.clipboard_table_actions_mixin.messagebox.showwarning") as warning:
                app.open_advanced_filter()
        warning.assert_called_once_with("提示", "当前 SQLite 数据库不存在，请先保存数据或选择已有数据库。")

        with patch("workflow.clipboard_table_actions_mixin.os.path.exists", return_value=True):
            app.open_advanced_filter()
        self.assertEqual(FakeWindowClass.calls, [app])

    def test_table_selection_loads_non_empty_table_name(self):
        app = FakeApp()

        app.on_table_selected()
        self.assertEqual(app.loaded_tables, [])

        app.table_name_var.set(" target ")
        app.on_table_selected()
        self.assertEqual(app.loaded_tables, ["target"])


if __name__ == "__main__":
    unittest.main()
