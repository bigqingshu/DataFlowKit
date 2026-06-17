# -*- coding: utf-8 -*-
import csv
import json
import os
import tempfile
import unittest

from workflow.table_access_audit_ui import (
    filter_table_access_audit_logs,
    table_access_audit_csv_fieldnames,
    table_access_audit_csv_row,
    table_access_audit_log_row,
    table_access_log_text,
    export_table_access_audit_logs,
)


class TableAccessAuditUiTests(unittest.TestCase):
    def test_log_text_and_tree_row_helpers(self):
        event = {
            "time": "2026-06-17 10:00:00",
            "node_name": "写入结果",
            "source_type": "SQLite表",
            "table_name": "orders",
            "operation_checked": "append_rows",
            "status": "ok",
            "write_mode": "append",
            "policy": "strict",
            "message": "允许写入",
        }

        self.assertIn("写入结果", table_access_log_text(event))
        self.assertEqual(
            table_access_audit_log_row(event),
            (
                "2026-06-17 10:00:00",
                "写入结果",
                "SQLite表",
                "orders",
                "append_rows",
                "ok",
                "append",
                "strict",
                "允许写入",
            ),
        )

    def test_filter_logs_counts_visible_and_tags(self):
        logs = [
            {"status": "ok", "message": "允许", "node_name": "节点A"},
            {"status": "denied", "message": "拒绝", "node_name": "节点B"},
            {"status": "", "message": "缺省", "node_name": "节点C"},
        ]

        result = filter_table_access_audit_logs(logs, selected_status="全部", keyword="节点")
        self.assertEqual(len(result["visible"]), 3)
        self.assertEqual(result["counts"], {"ok": 1, "denied": 1, "": 1})
        self.assertIn("最近日志 3 条，当前显示 3 条", result["summary"])
        self.assertEqual(result["visible"][1]["tag"], "denied")

        denied = filter_table_access_audit_logs(logs, selected_status="denied", keyword="拒绝")
        self.assertEqual([item["index"] for item in denied["visible"]], [1])
        self.assertIn("denied 1", denied["summary"])

    def test_csv_helpers_normalize_nested_values(self):
        logs = [
            {"status": "ok", "details": {"field": "A"}, "messages": ["a", "b"]},
            {"status": "warning", "extra": "x"},
        ]
        fieldnames = table_access_audit_csv_fieldnames(logs)

        self.assertEqual(fieldnames, ["details", "extra", "messages", "status"])
        row = table_access_audit_csv_row(logs[0], fieldnames)
        self.assertEqual(json.loads(row["details"]), {"field": "A"})
        self.assertEqual(json.loads(row["messages"]), ["a", "b"])
        self.assertEqual(row["extra"], "")

    def test_export_table_access_audit_logs_writes_csv(self):
        logs = [
            {"status": "ok", "details": {"field": "A"}},
            {"status": "warning", "details": {"field": "B"}},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "audit.csv")
            export_table_access_audit_logs(logs, path)
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))

        self.assertEqual(rows[0]["status"], "ok")
        self.assertEqual(json.loads(rows[1]["details"]), {"field": "B"})


if __name__ == "__main__":
    unittest.main()
