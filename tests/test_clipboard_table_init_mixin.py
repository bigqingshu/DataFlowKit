# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from workflow.clipboard_table_init_mixin import ClipboardTableInitMixin


class FakeVar:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value


class FakeRoot:
    def __init__(self):
        self.calls = []

    def title(self, value):
        self.calls.append(("title", value))

    def geometry(self, value):
        self.calls.append(("geometry", value))


class FakeApp(ClipboardTableInitMixin):
    def build_ui(self):
        self.ui_built = True


class ClipboardTableInitMixinTests(unittest.TestCase):
    def test_initializes_main_app_state_and_builds_ui(self):
        root = FakeRoot()

        with patch("workflow.clipboard_table_init_mixin.default_app_dir", return_value="C:\\app"):
            with patch("workflow.clipboard_table_init_mixin.tk.StringVar", new=FakeVar):
                with patch("workflow.clipboard_table_init_mixin.tk.BooleanVar", new=FakeVar):
                    app = FakeApp(root)

        self.assertEqual(root.calls, [
            ("title", "剪贴板表格解析器 - SQLite保存版"),
            ("geometry", "1420x760"),
        ])
        self.assertEqual(app.raw_data, "")
        self.assertEqual(app.headers, [])
        self.assertEqual(app.rows, [])
        self.assertFalse(app.edit_mode)
        self.assertIsNone(app.edit_entry)
        self.assertEqual(app.search_var.get(), "")
        self.assertEqual(app.search_matches, [])
        self.assertEqual(app.search_index, -1)
        self.assertEqual(app.app_dir, "C:\\app")
        self.assertEqual(app.db_path_var.get(), "C:\\app\\clipboard_tables.db")
        self.assertEqual(app.table_name_var.get(), "paste_table")
        self.assertTrue(app.first_row_header_var.get())
        self.assertTrue(app.recreate_table_var.get())
        self.assertEqual(app.edit_btn_text.get(), "修改模式:关")
        self.assertTrue(app.ui_built)


if __name__ == "__main__":
    unittest.main()
