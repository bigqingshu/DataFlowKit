# -*- coding: utf-8 -*-
import unittest

from workflow.nodes.data_nodes import (
    apply_copy_column_node,
    apply_copy_row_node,
    apply_delete_columns_node,
    apply_delete_rows_node,
    apply_move_columns_node,
)


class WorkflowDataNodesTests(unittest.TestCase):
    def test_delete_columns_keeps_order_and_normalizes_short_rows(self):
        headers, rows, message = apply_delete_columns_node(
            ["A", "B", "C"],
            [["a1", "b1", "c1"], ["a2"]],
            {"fields": ["B"]},
        )

        self.assertEqual(headers, ["A", "C"])
        self.assertEqual(rows, [["a1", "c1"], ["a2", ""]])
        self.assertEqual(message, "删除 1 列")

    def test_delete_unknown_column_is_noop(self):
        headers, rows, message = apply_delete_columns_node(
            ["A", "B"],
            [["a", "b", "ignored"]],
            {"fields": ["X"]},
        )

        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["a", "b"]])
        self.assertEqual(message, "删除 0 列")

    def test_move_columns_appends_unspecified_columns(self):
        headers, rows, message = apply_move_columns_node(
            ["A", "B", "C"],
            [["a1", "b1", "c1"], ["a2", "b2"]],
            {"order": ["C", "A"]},
        )

        self.assertEqual(headers, ["C", "A", "B"])
        self.assertEqual(rows, [["c1", "a1", "b1"], ["", "a2", "b2"]])
        self.assertEqual(message, "已调整列顺序")

    def test_move_columns_ignores_unknown_order_fields(self):
        headers, rows, _message = apply_move_columns_node(
            ["A", "B"],
            [["a", "b"]],
            {"order": ["X", "B"]},
        )

        self.assertEqual(headers, ["B", "A"])
        self.assertEqual(rows, [["b", "a"]])

    def test_copy_column_creates_unique_field_and_applies_empty_default(self):
        headers, rows, message = apply_copy_column_node(
            ["A", "A_复制"],
            [[" x "], [""]],
            {
                "source_field": "A",
                "new_field": "A_复制",
                "trim_value": True,
                "empty_default": "空",
            },
        )

        self.assertEqual(headers, ["A", "A_复制", "A_复制_2"])
        self.assertEqual(rows, [[" x ", "", "x"], ["", "", "空"]])
        self.assertEqual(message, "复制列为新字段 A_复制_2")

    def test_copy_column_overwrites_existing_or_creates_target(self):
        headers, rows, message = apply_copy_column_node(
            ["A"],
            [["x"]],
            {
                "source_field": "A",
                "output_mode": "覆盖已有字段",
                "target_field": "B",
            },
        )

        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["x", "x"]])
        self.assertEqual(message, "复制列并覆盖字段 B")

    def test_copy_row_supports_insert_modes(self):
        headers, rows, message = apply_copy_row_node(
            ["A", "B"],
            [["a1", "b1"], ["a2", "b2"]],
            {"source_row": "1", "copy_count": "2", "insert_mode": "原行下方"},
        )

        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["a1", "b1"], ["a1", "b1"], ["a1", "b1"], ["a2", "b2"]])
        self.assertEqual(message, "复制第 1 行 2 次")

    def test_delete_rows_by_list_range_condition_and_empty_rows(self):
        headers, rows, message = apply_delete_rows_node(
            ["A", "B"],
            [["1", "x"], ["2", "y"], ["3", "z"]],
            {"delete_mode": "按行号列表", "row_spec": "1,3"},
        )
        self.assertEqual(rows, [["2", "y"]])
        self.assertEqual(message, "删除 2 行")

        _headers, rows, _message = apply_delete_rows_node(
            headers,
            [["1", "x"], ["2", "y"], ["3", "z"]],
            {"delete_mode": "按行号范围", "start_row": "2", "end_row": "3"},
        )
        self.assertEqual(rows, [["1", "x"]])

        _headers, rows, _message = apply_delete_rows_node(
            headers,
            [["abc", "x"], ["def", "y"]],
            {"delete_mode": "按条件删除", "condition_field": "A", "condition_op": "包含", "condition_value": "b"},
        )
        self.assertEqual(rows, [["def", "y"]])

        _headers, rows, _message = apply_delete_rows_node(
            headers,
            [[None, ""], ["x", ""], ["", ""]],
            {"delete_mode": "删除空行", "empty_mode": "整行为空"},
        )
        self.assertEqual(rows, [["x", ""]])


if __name__ == "__main__":
    unittest.main()
