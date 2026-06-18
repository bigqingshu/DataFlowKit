# -*- coding: utf-8 -*-
import unittest

from workflow.nodes import data_nodes
from workflow.nodes.table_edit_nodes import (
    apply_copy_column_node,
    apply_copy_row_node,
    apply_delete_columns_node,
    apply_delete_rows_node,
    apply_move_columns_node,
    parse_row_spec_to_indexes,
)


class TableEditNodesTests(unittest.TestCase):
    def test_data_nodes_keeps_table_edit_compat_exports(self):
        self.assertIs(data_nodes.apply_delete_columns_node, apply_delete_columns_node)
        self.assertIs(data_nodes.apply_move_columns_node, apply_move_columns_node)
        self.assertIs(data_nodes.apply_copy_column_node, apply_copy_column_node)
        self.assertIs(data_nodes.apply_copy_row_node, apply_copy_row_node)
        self.assertIs(data_nodes.apply_delete_rows_node, apply_delete_rows_node)
        self.assertIs(data_nodes.parse_row_spec_to_indexes, parse_row_spec_to_indexes)

    def test_column_edit_nodes(self):
        headers, rows, message = apply_delete_columns_node(
            ["A", "B", "C"],
            [["a", "b", "c"]],
            {"fields": ["B"]},
        )
        self.assertEqual((headers, rows, message), (["A", "C"], [["a", "c"]], "删除 1 列"))

        headers, rows, message = apply_move_columns_node(
            ["A", "B", "C"],
            [["a", "b", "c"]],
            {"order": ["C", "A"]},
        )
        self.assertEqual((headers, rows, message), (["C", "A", "B"], [["c", "a", "b"]], "已调整列顺序"))

        headers, rows, message = apply_copy_column_node(
            ["A"],
            [[" x "], [""]],
            {"source_field": "A", "new_field": "B", "trim_value": True, "empty_default": "empty"},
        )
        self.assertEqual((headers, rows, message), (["A", "B"], [[" x ", "x"], ["", "empty"]], "复制列为新字段 B"))

    def test_row_edit_nodes(self):
        headers, rows, message = apply_copy_row_node(
            ["A"],
            [["a"], ["b"]],
            {"source_row": "2", "copy_count": "1", "insert_mode": "原行下方"},
        )
        self.assertEqual((headers, rows, message), (["A"], [["a"], ["b"], ["b"]], "复制第 2 行 1 次"))

        self.assertEqual(parse_row_spec_to_indexes("1, 3-4, 9", 4), {0, 2, 3})

        headers, rows, message = apply_delete_rows_node(
            ["A"],
            [["a"], [""], ["b"]],
            {"delete_mode": "删除空行", "empty_mode": "整行为空"},
        )
        self.assertEqual((headers, rows, message), (["A"], [["a"], ["b"]], "删除 1 行"))


if __name__ == "__main__":
    unittest.main()
