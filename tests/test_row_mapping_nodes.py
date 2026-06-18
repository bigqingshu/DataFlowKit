# -*- coding: utf-8 -*-
import unittest

from workflow.nodes import data_nodes
from workflow.nodes.row_mapping_nodes import apply_row_data_mapping_node, get_row_mapping_end_index


class RowMappingNodesTests(unittest.TestCase):
    def test_data_nodes_keeps_row_mapping_compat_exports(self):
        self.assertIs(data_nodes.apply_row_data_mapping_node, apply_row_data_mapping_node)
        self.assertIs(data_nodes.get_row_mapping_end_index, get_row_mapping_end_index)

    def test_row_mapping_end_index_modes(self):
        rows = [["a"], ["b"], ["c"]]
        self.assertEqual(get_row_mapping_end_index(rows, 1, {"end_mode": "固定行数", "count": "5"}), 2)
        self.assertEqual(get_row_mapping_end_index(rows, 0, {"end_mode": "填充到指定行", "end_row": "2"}), 1)
        self.assertEqual(get_row_mapping_end_index(rows, 1, {"end_mode": "填充到指定行", "end_row": "1"}), 1)
        self.assertEqual(get_row_mapping_end_index([], 0, {}), -1)

    def test_row_data_mapping_expands_and_handles_empty_values(self):
        headers, rows, message = apply_row_data_mapping_node(
            ["ID", "A", "B"],
            [["R1", " x ", ""], ["R2", "y", "z"]],
            {
                "keep_fields": ["ID"],
                "value_fields": ["A", "B"],
                "start_row": "1",
                "end_mode": "填充到数据边界",
                "empty_mode": "跳过空值",
                "trim_value": True,
            },
        )
        self.assertEqual(headers, ["ID", "原始行号", "来源字段", "输出内容", "状态"])
        self.assertEqual(rows, [["R1", "1", "A", "x", "成功"], ["R2", "2", "A", "y", "成功"], ["R2", "2", "B", "z", "成功"]])
        self.assertEqual(message, "按行取值展开 3 行，跳过空值 1 个")

    def test_row_data_mapping_empty_data_and_errors(self):
        headers, rows, message = apply_row_data_mapping_node(["A"], [], {"value_fields": ["A"]})
        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [])
        self.assertEqual(message, "当前无数据，未展开")

        with self.assertRaisesRegex(ValueError, "请至少选择一个取值字段"):
            apply_row_data_mapping_node(["A"], [["x"]], {"value_fields": ["Missing"]})
        with self.assertRaisesRegex(ValueError, "起始行号超出当前数据范围"):
            apply_row_data_mapping_node(["A"], [["x"]], {"value_fields": ["A"], "start_row": "2"})


if __name__ == "__main__":
    unittest.main()
