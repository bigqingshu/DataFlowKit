# -*- coding: utf-8 -*-
import unittest
from decimal import Decimal

from workflow.nodes import data_nodes
from workflow.nodes.numeric_column_nodes import (
    apply_numeric_column_node,
    format_numeric_column_result,
    get_numeric_node_row_indexes,
    numeric_node_fallback_value,
    parse_numeric_value_for_column_op,
)


class NumericColumnNodesTests(unittest.TestCase):
    def test_data_nodes_keeps_numeric_compat_exports(self):
        self.assertIs(data_nodes.apply_numeric_column_node, apply_numeric_column_node)
        self.assertIs(data_nodes.parse_numeric_value_for_column_op, parse_numeric_value_for_column_op)
        self.assertIs(data_nodes.format_numeric_column_result, format_numeric_column_result)
        self.assertIs(data_nodes.get_numeric_node_row_indexes, get_numeric_node_row_indexes)
        self.assertIs(data_nodes.numeric_node_fallback_value, numeric_node_fallback_value)

    def test_numeric_helpers(self):
        self.assertEqual(parse_numeric_value_for_column_op(" 10.50 "), Decimal("10.50"))
        with self.assertRaisesRegex(ValueError, "空值"):
            parse_numeric_value_for_column_op("")
        self.assertEqual(format_numeric_column_result(Decimal("1.2300"), {"decimal_places": "自动"}), "1.23")
        self.assertEqual(format_numeric_column_result(Decimal("1.235"), {"decimal_places": "2"}), "1.24")
        self.assertEqual(numeric_node_fallback_value("old", "填写固定值", "fixed", "计算失败"), "fixed")

    def test_numeric_row_range_and_node_execution(self):
        headers = ["A", "Ref"]
        rows = [["1", "x"], ["2", ""], ["3", "y"]]
        self.assertEqual(
            get_numeric_node_row_indexes(headers, rows, {"range_mode": "指定起止行", "start_row": "2", "end_row": "3"}),
            [1, 2],
        )
        self.assertEqual(
            get_numeric_node_row_indexes(
                headers,
                rows,
                {"range_mode": "填充到参考列数据边界", "start_row": "1", "reference_field": "Ref"},
            ),
            [0, 1, 2],
        )

        headers, rows, message = apply_numeric_column_node(
            ["A"],
            [["2"], ["bad"]],
            {
                "target_field": "A",
                "operation": "乘",
                "operand_source": "固定值",
                "operand_value": "3",
                "output_field": "B",
                "non_number_policy": "标记为计算失败",
            },
        )
        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["2", "6"], ["bad", "计算失败"]])
        self.assertEqual(message, "列数字运算完成：成功 1 行，非数字/运算失败 1 行")


if __name__ == "__main__":
    unittest.main()
