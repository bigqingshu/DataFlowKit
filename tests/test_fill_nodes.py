# -*- coding: utf-8 -*-
import unittest

from workflow.nodes import data_nodes
from workflow.nodes.fill_nodes import (
    apply_area_fill_node,
    apply_fill_value_node,
    apply_sequence_fill_node,
    format_sequence_value,
    get_config_cell_value,
    should_write_cell,
)


class FillNodesTests(unittest.TestCase):
    def test_data_nodes_keeps_fill_compat_exports(self):
        self.assertIs(data_nodes.apply_fill_value_node, apply_fill_value_node)
        self.assertIs(data_nodes.apply_sequence_fill_node, apply_sequence_fill_node)
        self.assertIs(data_nodes.apply_area_fill_node, apply_area_fill_node)
        self.assertIs(data_nodes.get_config_cell_value, get_config_cell_value)
        self.assertIs(data_nodes.format_sequence_value, format_sequence_value)
        self.assertIs(data_nodes.should_write_cell, should_write_cell)

    def test_fill_value_manual_and_same_row_source(self):
        headers, rows, message = apply_fill_value_node(
            ["A"],
            [["old"], [""]],
            {
                "target_field": "A",
                "value_source": "手动输入值",
                "manual_value": "new",
                "direction": "向下",
                "end_mode": "固定数量",
                "count": "3",
                "overwrite_rule": "只填充空单元格",
            },
        )
        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["old"], ["new"], ["new"]])
        self.assertEqual(message, "填充 2 个单元格，跳过 1 个")

        headers, rows, message = apply_fill_value_node(
            ["Source", "Target"],
            [["s1", ""], ["s2", "occupied"]],
            {
                "target_field": "Target",
                "value_source": "同行来源字段",
                "source_field": "Source",
                "direction": "向下",
                "end_mode": "固定数量",
                "count": "2",
                "overwrite_rule": "覆盖所有目标单元格",
            },
        )
        self.assertEqual(rows, [["s1", "s1"], ["s2", "s2"]])
        self.assertEqual(message, "填充 2 个单元格，跳过 0 个")

    def test_sequence_fill_and_helpers(self):
        self.assertEqual(format_sequence_value(7, {"zero_pad": "3", "prefix": "NO-", "suffix": "-X"}), "NO-007-X")
        self.assertEqual(should_write_cell("x", "只填充空单元格"), (False, False))

        headers, rows, message = apply_sequence_fill_node(
            ["Seq"],
            [[""], ["keep"], [""]],
            {
                "target_field": "Seq",
                "start_value": "7",
                "step": "2",
                "zero_pad": "3",
                "prefix": "NO-",
                "suffix": "-X",
                "direction": "向下",
                "end_mode": "固定数量",
                "count": "3",
                "overwrite_rule": "不覆盖已有数据，只跳过",
            },
        )
        self.assertEqual(rows, [["NO-007-X"], ["keep"], ["NO-009-X"]])
        self.assertEqual(message, "序列填充 2 个单元格，跳过 1 个")

    def test_area_fill_manual_and_source_area_copy(self):
        headers, rows, message = apply_area_fill_node(
            ["A", "B"],
            [["", ""], ["", "occupied"]],
            {
                "start_field": "A",
                "end_field": "B",
                "start_row": "1",
                "end_row": "2",
                "value_source": "手动输入值",
                "manual_value": "x",
                "overwrite_rule": "只填充空单元格",
            },
        )
        self.assertEqual(rows, [["x", "x"], ["x", "occupied"]])
        self.assertEqual(message, "区域填充 3 个单元格，跳过 1 个")

        headers, rows, message = apply_area_fill_node(
            ["S1", "S2", "T"],
            [["a1", "b1", ""], ["a2", "b2", ""]],
            {
                "start_field": "T",
                "end_field": "T",
                "start_row": "1",
                "value_source": "来源区域完整复制",
                "source_field": "S1",
                "source_end_field": "S2",
                "source_range_mode": "整体表格数据边界",
                "overwrite_rule": "覆盖所有目标单元格",
            },
        )
        self.assertEqual(headers, ["S1", "S2", "T", "区域复制列4"])
        self.assertEqual(rows, [["a1", "b1", "a1", "b1"], ["a2", "b2", "a2", "b2"]])
        self.assertEqual(message, "来源区域完整复制 4 个单元格，跳过 0 个")


if __name__ == "__main__":
    unittest.main()
