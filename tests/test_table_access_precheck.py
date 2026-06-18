# -*- coding: utf-8 -*-
import unittest

from workflow import table_access_precheck
from workflow import table_access_precheck_display
from workflow import table_access_precheck_fields
from workflow.table_access_precheck import (
    evaluate_expected_table_access,
    evaluate_field_access,
    evaluate_field_mapping_access,
    evaluate_node_table_access_precheck,
    evaluate_plugin_access_declaration_precheck,
    evaluate_unmatched_actual_table_access,
    evaluate_workflow_output_precheck,
    find_table_access_field_rule,
    find_matching_table_access_entry,
    iter_nodes_for_table_access_precheck,
    make_table_access_precheck_issue,
    make_workflow_output_access_entry,
    normalize_precheck_transit_name,
    table_access_field_items,
    table_access_entry_match_score,
    table_access_entry_status,
    table_access_entry_table_label,
    table_access_operation_summary,
    table_access_precheck_actionable,
    table_access_precheck_blocking,
    table_access_precheck_sort_key,
    table_access_precheck_summary_text,
)


class TableAccessPrecheckHelperTests(unittest.TestCase):
    def test_display_helpers_are_compatible_exports(self):
        self.assertIs(
            table_access_precheck.table_access_entry_status,
            table_access_precheck_display.table_access_entry_status,
        )
        self.assertIs(
            table_access_precheck.table_access_precheck_summary_text,
            table_access_precheck_display.table_access_precheck_summary_text,
        )
        self.assertIs(
            table_access_precheck.iter_nodes_for_table_access_precheck,
            table_access_precheck_display.iter_nodes_for_table_access_precheck,
        )

    def test_field_helpers_are_compatible_exports(self):
        self.assertIs(
            table_access_precheck.table_access_field_items,
            table_access_precheck_fields.table_access_field_items,
        )
        self.assertIs(
            table_access_precheck.evaluate_field_mapping_access,
            table_access_precheck_fields.evaluate_field_mapping_access,
        )

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

    def test_field_mapping_items_and_rule_matching_helpers(self):
        dict_entry = {
            "field_mapping": {
                "a": {"source_field": "A", "target_field": "B"},
                "bad": "skip",
            }
        }
        self.assertEqual(table_access_field_items(dict_entry), [("a", {"source_field": "A", "target_field": "B"})])
        self.assertEqual(find_table_access_field_rule(dict_entry, target="B")["source_field"], "A")

        list_entry = {
            "field_mapping_mode": "by_order",
            "field_mapping": [
                {"key": "first", "source_index": 1, "target_field": "A"},
                {"source_index": 2, "target_field": "B"},
            ],
        }
        self.assertEqual([key for key, _item in table_access_field_items(list_entry)], ["first", "field_2"])
        self.assertEqual(find_table_access_field_rule(list_entry, field_index=1)["target_field"], "B")

    def test_field_mapping_access_helper_checks_matching_actual_rules(self):
        expected = {
            "table": "src",
            "permissions": {"read_table": True},
            "field_mapping": {
                "a": {
                    "source_field": "A",
                    "target_field": "A",
                    "permissions": {"write_field": True, "read_field": True},
                }
            },
        }
        actual = {
            "table": "src",
            "field_mapping": {
                "a": {
                    "source_field": "A",
                    "target_field": "A",
                    "permissions": {"protect_field": True, "read_field": False},
                }
            },
        }

        issues = evaluate_field_mapping_access("1.字段", {"type": "字段"}, expected, actual)
        self.assertEqual([item["severity"] for item in issues], ["error", "warning"])
        self.assertTrue(any("字段被保护" in item["message"] for item in issues))
        self.assertTrue(any("字段读权限被关闭" in item["message"] for item in issues))

    def test_table_entry_match_and_find_helpers(self):
        expected = {"table": "源 表", "source_type": "SQLite表", "role": "source"}
        actual = {"table": "源_表", "source_type": "SQLite表", "role": "source"}
        self.assertGreater(table_access_entry_match_score(actual, expected), 0)

        pattern_actual = {"table_pattern": "src_*", "source_type": "SQLite表"}
        pattern_expected = {"table": "src_demo", "source_type": "SQLite表"}
        self.assertIs(find_matching_table_access_entry([pattern_actual], pattern_expected), pattern_actual)

    def test_node_table_access_precheck_helper_orchestrates_node_issues(self):
        expected_access = {
            "tables": [{
                "role": "target",
                "source_type": "中转副表",
                "table": "中转: tmp",
                "permissions": {"write_table": True, "create_table": True},
                "field_mapping": {
                    "a": {
                        "source_field": "A",
                        "target_field": "A",
                        "permissions": {"write_field": True},
                    }
                },
            }]
        }
        actual_access = {
            "tables": [
                {
                    "role": "target",
                    "source_type": "中转副表",
                    "table": "中转: tmp",
                    "permissions": {"write_table": True, "create_table": True},
                    "field_mapping": {
                        "a": {
                            "source_field": "A",
                            "target_field": "A",
                            "permissions": {"protect_field": True},
                        }
                    },
                },
                {"role": "manual", "source_type": "SQLite表", "table": "danger", "permissions": {"drop_table": True}},
            ]
        }

        result = evaluate_node_table_access_precheck(
            "1.节点",
            {"type": "节点"},
            expected_access,
            actual_access,
        )

        self.assertEqual(result["produced_transit"], ["tmp"])
        messages = [item["message"] for item in result["issues"]]
        self.assertTrue(any("字段被保护" in message for message in messages))
        self.assertTrue(any("手动表角色包含高风险写入权限" in message for message in messages))

    def test_node_table_access_precheck_helper_includes_plugin_declaration_warning(self):
        result = evaluate_node_table_access_precheck(
            "1.插件",
            {"type": "插件节点", "config": {"plugin_id": "p1"}},
            {"tables": []},
            {"tables": []},
            needs_plugin_declaration=True,
            has_plugin_declaration=False,
        )

        self.assertEqual(len(result["issues"]), 1)
        self.assertIn("未声明表权限规格", result["issues"][0]["message"])

    def test_workflow_output_precheck_helper(self):
        self.assertEqual(evaluate_workflow_output_precheck("输出到主界面预览区", "", db_path=""), [])

        issues = evaluate_workflow_output_precheck("保存为SQLite新表", "", db_path="")
        messages = [item["message"] for item in issues]
        self.assertIn("输出方式需要 SQLite 数据库，但当前未设置数据库路径。", messages)
        self.assertIn("输出方式需要表名，但输出表名为空。", messages)
        self.assertTrue(all(item["blocking"] for item in issues))

        overwrite_issues = evaluate_workflow_output_precheck("覆盖当前表", "目标表", db_path="demo.db")
        self.assertEqual(len(overwrite_issues), 1)
        self.assertEqual(overwrite_issues[0]["category"], "risk")
        self.assertFalse(overwrite_issues[0]["blocking"])
        self.assertIn("覆盖 SQLite 表：目标表", overwrite_issues[0]["message"])

        entry = make_workflow_output_access_entry("目标表", "覆盖当前表")
        self.assertTrue(entry["permissions"]["replace_table"])
        self.assertEqual(entry["role"], "workflow_output")

    def test_plugin_access_declaration_precheck_helper(self):
        node = {"type": "插件节点"}
        config = {"plugin_id": "p1"}

        issues = evaluate_plugin_access_declaration_precheck(
            "1.插件节点",
            node,
            config,
            needs_declaration=True,
            has_declaration=False,
        )
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["table"], "p1")
        self.assertIn("未声明表权限规格", issues[0]["message"])

        self.assertEqual(
            evaluate_plugin_access_declaration_precheck("1.插件节点", node, config, True, True),
            [],
        )
        self.assertEqual(
            evaluate_plugin_access_declaration_precheck("1.普通节点", {"type": "筛选"}, config, True, False),
            [],
        )


if __name__ == "__main__":
    unittest.main()
