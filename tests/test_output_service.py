# -*- coding: utf-8 -*-
import zipfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from db.table_manager import TableAccessManager
from engine.headless import HeadlessWorkflowEngine
from engine.stdio_worker import StdioWorker


def request(action, payload=None, request_id="req1"):
    return {
        "request_id": request_id,
        "api_version": "1.0",
        "action": action,
        "payload": payload or {},
    }


class OutputServiceTests(unittest.TestCase):
    def test_output_service_lists_modes_and_prepares_preview_output(self):
        engine = HeadlessWorkflowEngine()

        modes = engine.list_output_modes()
        output = engine.apply_output(
            headers=["A"],
            rows=[["a"]],
            logs=["done"],
            output_mode="输出到主界面预览区",
        )

        self.assertTrue(modes["ok"])
        self.assertEqual(modes["modes"][0]["mode"], "输出到主界面预览区")
        self.assertTrue(output["ok"])
        self.assertEqual(output["action"]["type"], "update_frontend_table")
        self.assertEqual(output["table"]["headers"], ["A"])
        self.assertEqual(output["logs"], ["done"])

    def test_output_service_requires_targets_before_side_effect_writes(self):
        engine = HeadlessWorkflowEngine()

        output = engine.apply_output(
            headers=["A"],
            rows=[["a"]],
            output_mode="保存为SQLite新表",
            output_table="结果表",
        )
        missing_target = engine.apply_output(
            headers=["A"],
            rows=[["a"]],
            output_mode="覆盖当前表",
            output_table="",
        )

        self.assertFalse(output["ok"])
        self.assertEqual(output["issues"][0]["code"], "missing_db_path")
        self.assertFalse(missing_target["ok"])
        self.assertEqual(missing_target["issues"][0]["code"], "missing_output_table")

    def test_output_service_writes_sqlite_new_and_overwrite_with_backup(self):
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "out.db")
            engine = HeadlessWorkflowEngine()

            first = engine.apply_output(
                headers=["A"],
                rows=[["old"]],
                output_mode="保存为SQLite新表",
                output_table="结果表",
                db_path=db_path,
            )
            overwrite = engine.apply_output(
                headers=["A"],
                rows=[["new"]],
                output_mode="覆盖当前表",
                output_table="结果表",
                db_path=db_path,
                backup_before_overwrite=True,
            )
            manager = TableAccessManager(db_path)
            data = manager.read_table("结果表")

            self.assertTrue(first["ok"])
            self.assertEqual(first["action"]["type"], "write_sqlite_table")
            self.assertTrue(overwrite["ok"])
            self.assertEqual(overwrite["service_result"]["backup_table"].startswith("结果表_backup_"), True)
            self.assertEqual(data["headers"], ["A"])
            self.assertEqual(data["rows"], [["new"]])
            self.assertIn(overwrite["service_result"]["backup_table"], manager.list_tables())

    def test_output_service_exports_xlsx_file(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "out.xlsx"
            engine = HeadlessWorkflowEngine()

            output = engine.apply_output(
                headers=["A", "B"],
                rows=[["a", 1]],
                output_mode="导出为xlsx",
                output_table="结果表",
                output_path=str(path),
            )

            self.assertTrue(output["ok"])
            self.assertEqual(output["action"]["type"], "export_xlsx")
            self.assertTrue(path.exists())
            with zipfile.ZipFile(path) as archive:
                self.assertIn("xl/worksheets/sheet1.xml", archive.namelist())

    def test_stdio_worker_exposes_output_actions(self):
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "stdio.db")
            worker = StdioWorker()

            modes = worker.handle_request(request("list_output_modes"))
            output = worker.handle_request(request("apply_output", {
                "headers": ["A"],
                "rows": [["a"]],
                "logs": ["done"],
                "output_mode": "保存为SQLite新表",
                "output_table": "stdio_result",
                "db_path": db_path,
            }))

            self.assertTrue(modes["ok"])
            self.assertEqual(modes["result"]["modes"][0]["mode"], "输出到主界面预览区")
            self.assertTrue(output["ok"])
            self.assertTrue(output["result"]["ok"])
            self.assertEqual(output["result"]["action"]["type"], "write_sqlite_table")
            self.assertEqual(TableAccessManager(db_path).read_table("stdio_result")["rows"], [["a"]])


if __name__ == "__main__":
    unittest.main()
