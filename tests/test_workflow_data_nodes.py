# -*- coding: utf-8 -*-
import unittest

from workflow.nodes.data_nodes import apply_delete_columns_node, apply_move_columns_node


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


if __name__ == "__main__":
    unittest.main()

