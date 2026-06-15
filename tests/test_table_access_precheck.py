# -*- coding: utf-8 -*-
import unittest

from workflow.table_access_precheck import (
    evaluate_expected_table_access,
    evaluate_field_access,
    evaluate_unmatched_actual_table_access,
    iter_nodes_for_table_access_precheck,
    make_table_access_precheck_issue,
    normalize_precheck_transit_name,
    table_access_entry_status,
    table_access_entry_table_label,
    table_access_operation_summary,
    table_access_precheck_actionable,
    table_access_precheck_blocking,
    table_access_precheck_sort_key,
    table_access_precheck_summary_text,
)


class TableAccessPrecheckHelperTests(unittest.TestCase):
    def test_issue_summary_actionable_blocking_and_sorting(self):
        issues = [
            make_table_access_precheck_issue(
                "info",
                "2.节点",
                {"type": "节点", "name": "n2"},
                {"table": "b", "permissions": {"read_table": True}},
                "info message",
                blocking=False,
            ),
            make_table_access_precheck_issue(
                "warning",
                "1.节点",
                {"type": "节点", "name": "n1"},
                {"table": "a", "permissions": {"write_table": True}},
                "warning message",
            ),
            make_table_access_precheck_issue(
                "error",
                "3.节点",
                {"type": "节点", "name": "n3"},
                {"table_pattern": "src_*", "permissions": {"replace_table": True}},
                "error message",
                category="risk",
                blocking=False,
            ),
        ]

        self.assertEqual([item["severity"] for item in table_access_precheck_actionable(issues)], ["warning", "error"])
        self.assertEqual(table_access_precheck_blocking(issues), [issues[1]])
        self.assertIn("错误 1 项", table_access_precheck_summary_text(issues))
        self.assertIn("阻断 1 项", table_access_precheck_summary_text(issues))
        self.assertEqual([item["severity"] for item in sorted(issues, key=table_access_precheck_sort_key)], ["error", "warning", "info"])

    def test_table_label_operation_and_status_helpers(self):
        entry = {
            "table_pattern": "src_*",
            "permissions": {"read_table": True, "write_table": True, "replace_table": True},
            "write_mode": "replace",
        }

        self.assertEqual(table_access_entry_table_label(entry), "范围:src_*")
        self.assertEqual(table_access_operation_summary(entry, write_mode_formatter=lambda mode: "覆盖"), "读表/写表/替换；覆盖")
        self.assertEqual(table_access_entry_status(entry), "危险写入")
        self.assertEqual(table_access_entry_status({"table": "x", "permissions": {}}), "未授权")
        self.assertEqual(table_access_entry_status({"table": "__CURRENT_TABLE__", "is_current_table": True, "permissions": {"read_table": True}}), "当前表读取")

    def test_iter_nodes_and_transit_name_normalization(self):
        nodes = [
            {"type": "A"},
            {"type": "组", "config": {"nodes": [{"type": "B"}, {"type": "C"}]}},
            {"type": "D"},
        ]

        labels = [label for label, _node in iter_nodes_for_table_access_precheck(nodes, stop_index=1)]
        self.assertEqual(labels, ["1.A", "2.组", "2.组 > 1.B", "2.组 > 2.C"])
        self.assertEqual(normalize_precheck_transit_name("中转: tmp"), "tmp")
        self.assertEqual(normalize_precheck_transit_name("普通表"), "普通表")

    def test_expected_table_access_reports_missing_actual_and_risks(self):
        expected = {
            "role": "target",
            "source_type": "SQLite表",
            "table": "out",
            "permissions": {"read_table": True, "write_table": True, "replace_table": True},
        }

        result = evaluate_expected_table_access(
            "1.写入",
            {"type": "写入"},
            expected,
            actual=None,
            permission_label_map={"write_table": "写表", "replace_table": "替换表"},
            db_path="",
            sqlite_tables=None,
        )

        messages = [item["message"] for item in result["issues"]]
        self.assertIn("当前 table_access 中缺少该表角色。", messages)
        self.assertIn("节点需要访问 SQLite 表，但当前未设置数据库路径。", messages)
        self.assertTrue(any("高风险写入权限" in message for message in messages))
        self.assertEqual(result["issues"][0]["severity"], "error")

    def test_expected_table_access_reports_missing_permissions_and_sqlite_source(self):
        expected = {
            "role": "source",
            "source_type": "SQLite表",
            "table": "src",
            "permissions": {"read_table": True},
        }
        actual = {
            "role": "source",
            "source_type": "SQLite表",
            "table": "src",
            "permissions": {"read_table": False},
        }

        result = evaluate_expected_table_access(
            "1.筛选",
            {"type": "筛选"},
            expected,
            actual=actual,
            permission_label_map={"read_table": "读表"},
            db_path="demo.db",
            db_exists=True,
            sqlite_tables={"other"},
        )

        messages = [item["message"] for item in result["issues"]]
        self.assertIn("实际授权缺少：读表。", messages)
        self.assertIn("SQLite 来源表不存在：src", messages)

    def test_expected_table_access_tracks_transit_producers_and_missing_reader(self):
        writer = {
            "source_type": "中转副表",
            "table": "中转: tmp",
            "permissions": {"write_table": True, "create_table": True},
        }
        reader = {
            "source_type": "中转副表",
            "table": "中转: tmp",
            "permissions": {"read_table": True},
        }

        writer_result = evaluate_expected_table_access("1.保存", {"type": "保存"}, writer, actual=writer)
        self.assertEqual(writer_result["produced_transit"], ["tmp"])

        missing_reader = evaluate_expected_table_access("2.读取", {"type": "读取"}, reader, actual=reader, produced_transit=set())
        self.assertTrue(any("未看到生成者" in item["message"] for item in missing_reader["issues"]))

        ok_reader = evaluate_expected_table_access("2.读取", {"type": "读取"}, reader, actual=reader, produced_transit={"tmp"})
        self.assertFalse(any("未看到生成者" in item["message"] for item in ok_reader["issues"]))

    def test_field_and_unmatched_actual_access_helpers(self):
        field_issues = evaluate_field_access(
            "1.写字段",
            {"type": "写字段"},
            {"table": "src", "permissions": {"read_table": True}},
            "A",
            {"write_field": True, "read_field": True},
            {"protect_field": True, "read_field": False},
        )
        self.assertEqual([item["severity"] for item in field_issues], ["error", "warning"])

        unbound = evaluate_unmatched_actual_table_access("1.节点", {"type": "节点"}, {"table": "", "permissions": {}})
        self.assertTrue(any("手动表角色状态异常" in item["message"] for item in unbound))

        risky = evaluate_unmatched_actual_table_access("1.节点", {"type": "节点"}, {"table": "src", "permissions": {"drop_table": True}})
        self.assertEqual(risky[0]["category"], "risk")
        self.assertFalse(risky[0]["blocking"])


if __name__ == "__main__":
    unittest.main()
