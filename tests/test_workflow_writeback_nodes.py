# -*- coding: utf-8 -*-
import unittest

from workflow.nodes.writeback_nodes import (
    apply_external_table_to_current_node,
    build_writeback_actions,
    build_writeback_full_structure_rows_for_sqlite,
    compare_writeback_values,
)
from DataFlowKit import PlanWorkflowWindow


class WorkflowWritebackNodesTests(unittest.TestCase):
    def test_dataflowkit_writeback_config_errors_happen_before_sqlite_read(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)

        def fail_read(*_args, **_kwargs):
            raise AssertionError("should not read table before config validation")

        window.load_target_table_rows_for_writeback = fail_read

        with self.assertRaisesRegex(ValueError, "匹配规则"):
            window.build_writeback_actions(
                ["id"],
                [["A"]],
                {
                    "target_table": "target",
                    "use_match_rules": True,
                    "match_rules": [],
                    "field_mappings": [{"source_field": "id", "target_field": "id"}],
                },
            )

        with self.assertRaisesRegex(ValueError, "字段映射规则"):
            window.apply_external_table_to_current_node(
                ["id"],
                [["A"]],
                {
                    "source_table": "source",
                    "use_match_rules": False,
                    "field_mappings": [],
                },
            )

    def test_compare_writeback_values_supports_alias_operators(self):
        self.assertTrue(compare_writeback_values("abc", "等于", "abc"))
        self.assertTrue(compare_writeback_values("abc", "不等于", "ab"))
        self.assertTrue(compare_writeback_values("abc", "当前包含目标", "b"))
        self.assertTrue(compare_writeback_values("abc", "当前包含外部", "b"))
        self.assertTrue(compare_writeback_values("a", "目标包含当前", "cat"))
        self.assertTrue(compare_writeback_values("a", "外部包含当前", "cat"))
        self.assertTrue(compare_writeback_values("abc", "双向包含", "b"))
        self.assertFalse(compare_writeback_values("abc", "当前包含目标", ""))

    def test_build_writeback_full_structure_rows_for_sqlite_maps_source_rows(self):
        actions, new_rows = build_writeback_full_structure_rows_for_sqlite(
            ["id", "name"],
            [["1", "Alice"], ["2", ""]],
            {
                "field_mappings": [
                    {"source_field": "id", "target_field": "tid"},
                    {"source_field": "name", "target_field": "tname"},
                ],
                "source_empty_policy": "写入固定值",
                "source_empty_fixed": "N/A",
            },
            ["tid", "tname", "keep_empty"],
        )

        self.assertEqual(new_rows, [["1", "Alice", ""], ["2", "N/A", ""]])
        self.assertEqual(len(actions), 4)
        self.assertEqual(sum(1 for action in actions if action["write"]), 4)
        self.assertEqual(actions[0]["new_row_key"], "full_1")

    def test_build_writeback_actions_uses_match_rules_and_overwrite_policy(self):
        actions = build_writeback_actions(
            ["id", "value"],
            [["A", "new"], ["B", "same"], ["C", "missing"]],
            {
                "use_match_rules": True,
                "match_rules": [{"source_field": "id", "target_field": "id", "operator": "等于"}],
                "field_mappings": [{"source_field": "value", "target_field": "value"}],
                "overwrite_policy": "目标已有值且不同才覆盖",
            },
            ["id", "value"],
            [
                {"__rowid__": 1, "__row_index__": 1, "id": "A", "value": "old"},
                {"__rowid__": 2, "__row_index__": 2, "id": "B", "value": "same"},
            ],
        )

        self.assertEqual([action["match_status"] for action in actions], ["成功", "成功", "未匹配"])
        self.assertEqual([action["write"] for action in actions], [True, False, False])
        self.assertEqual(actions[0]["action"], "不同，将覆盖")
        self.assertEqual(actions[1]["action"], "相同，跳过")

    def test_build_writeback_actions_can_plan_new_rows_by_sequence(self):
        actions = build_writeback_actions(
            ["value"],
            [["first"], ["second"]],
            {
                "use_match_rules": False,
                "field_mappings": [{"source_field": "value", "target_field": "value"}],
                "overwrite_policy": "覆盖全部",
                "sequential_insert_missing_rows": True,
            },
            ["value"],
            [{"__rowid__": 1, "__row_index__": 1, "value": "old"}],
        )

        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[1]["target_row_index"], "新增第2行")
        self.assertTrue(actions[1]["is_new_row"])
        self.assertEqual(actions[1]["new_row_key"], "source_2")

    def test_apply_external_table_to_current_node_adds_fields_and_rows(self):
        headers, rows, stat = apply_external_table_to_current_node(
            ["id", "current"],
            [["A", "keep"]],
            {
                "use_match_rules": False,
                "field_mappings": [{"source_field": "value", "target_field": "external_value"}],
                "overwrite_policy": "覆盖全部",
                "sequential_insert_missing_rows": True,
            },
            ["value"],
            [
                {"__rowid__": 1, "__row_index__": 1, "value": "x"},
                {"__rowid__": 2, "__row_index__": 2, "value": "y"},
            ],
        )

        self.assertEqual(headers, ["id", "current", "external_value"])
        self.assertEqual(rows, [["A", "keep", "x"], ["", "", "y"]])
        self.assertIn("写入 2 个单元格", stat)
        self.assertIn("新增字段 1 个", stat)
        self.assertIn("新增当前行 1 行", stat)

    def test_apply_external_table_full_structure_discards_old_extra_rows(self):
        headers, rows, stat = apply_external_table_to_current_node(
            ["id", "old"],
            [["A", "old-a"], ["B", "old-b"], ["C", "old-c"]],
            {
                "write_range_mode": "按来源完整结构覆盖",
                "use_match_rules": False,
                "field_mappings": [{"source_field": "value", "target_field": "new_value"}],
                "source_empty_policy": "跳过",
            },
            ["value"],
            [
                {"__rowid__": 1, "__row_index__": 1, "value": "x"},
                {"__rowid__": 2, "__row_index__": 2, "value": ""},
            ],
        )

        self.assertEqual(headers, ["id", "old", "new_value"])
        self.assertEqual(rows, [["", "", "x"], ["", "", ""]])
        self.assertIn("按来源完整结构覆盖", stat)
        self.assertIn("写入 1 个单元格", stat)


if __name__ == "__main__":
    unittest.main()
