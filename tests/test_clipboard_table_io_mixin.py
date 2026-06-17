# -*- coding: utf-8 -*-
import os
import sqlite3
import tempfile
import unittest
import zipfile

from workflow.clipboard_table_io_mixin import ClipboardTableIoMixin


class FakeVar:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeCombo(dict):
    pass


class ClipboardTableIoFakeApp(ClipboardTableIoMixin):
    def __init__(self, db_path):
        self.db_path_var = FakeVar(db_path)
        self.table_name_var = FakeVar("paste_table")
        self.recreate_table_var = FakeVar(True)
        self.info_var = FakeVar("")
        self.headers = []
        self.rows = []
        self.raw_data = ""
        self.table_combo = FakeCombo()
        self.refresh_count = 0
        self.edit_entry = None

    def make_display_headers(self, headers):
        return list(headers)

    def refresh_tree(self):
        self.refresh_count += 1


class ClipboardTableIoMixinTests(unittest.TestCase):
    def test_save_and_load_rows_to_sqlite(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmp:
            db_path = os.path.join(tmp, "clipboard.db")
            app = ClipboardTableIoFakeApp(db_path)

            saved_name, row_count = app.save_rows_to_sqlite_table(
                "客户 表",
                ["姓名", "年龄"],
                [["Alice", 20], ["Bob"]],
                recreate=True,
            )

            self.assertEqual(saved_name, "客户_表")
            self.assertEqual(row_count, 2)
            self.assertIn("客户_表", app.get_table_names())
            self.assertEqual(app.table_combo["values"], ["客户_表"])

            app.load_table_from_sqlite(saved_name)

        self.assertEqual(app.headers, ["姓名", "年龄"])
        self.assertEqual(app.rows, [["Alice", "20"], ["Bob", ""]])
        self.assertEqual(app.refresh_count, 1)
        self.assertIn("已加载数据库表", app.info_var.get())

    def test_get_available_table_name_uses_timestamp_suffix(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmp:
            db_path = os.path.join(tmp, "clipboard.db")
            app = ClipboardTableIoFakeApp(db_path)
            conn = sqlite3.connect(db_path)
            try:
                conn.execute('CREATE TABLE "demo" ("a" TEXT)')
                name = app.get_available_table_name(conn, "demo")
            finally:
                conn.close()

        self.assertRegex(name, r"^demo_\d{8}_\d{6}$")

    def test_minimal_xlsx_export_contains_rows(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmp:
            path = os.path.join(tmp, "out.xlsx")
            app = ClipboardTableIoFakeApp(os.path.join(tmp, "clipboard.db"))
            app.table_name_var.set("导出表")
            app.export_xlsx_minimal(
                path,
                headers=["姓名", "备注"],
                rows=[["Alice", "A&B"], ["Bob", None]],
                table_name="导出表",
            )

            with zipfile.ZipFile(path) as zf:
                sheet_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
                workbook_xml = zf.read("xl/workbook.xml").decode("utf-8")

        self.assertIn("姓名", sheet_xml)
        self.assertIn("Alice", sheet_xml)
        self.assertIn("A&amp;B", sheet_xml)
        self.assertIn('sheet name="导出表"', workbook_xml)


if __name__ == "__main__":
    unittest.main()
