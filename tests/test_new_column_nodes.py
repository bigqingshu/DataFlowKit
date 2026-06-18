# -*- coding: utf-8 -*-
import unittest
from datetime import datetime

from workflow.nodes import data_nodes
from workflow.nodes.new_column_nodes import (
    apply_current_datetime_column_node,
    apply_new_columns_node,
    parse_new_columns_specs,
    render_current_datetime_template,
)


class NewColumnNodesTests(unittest.TestCase):
    def test_data_nodes_keeps_new_column_compat_exports(self):
        self.assertIs(data_nodes.apply_new_columns_node, apply_new_columns_node)
        self.assertIs(data_nodes.parse_new_columns_specs, parse_new_columns_specs)
        self.assertIs(data_nodes.apply_current_datetime_column_node, apply_current_datetime_column_node)
        self.assertIs(data_nodes.render_current_datetime_template, render_current_datetime_template)

    def test_parse_and_apply_new_columns(self):
        self.assertEqual(
            parse_new_columns_specs({"columns_text": "A=1\nB=2", "value_mode": "按列配置值"}),
            [("A", "1"), ("B", "2")],
        )
        headers, rows, message = apply_new_columns_node(
            ["A"],
            [["old"]],
            {"columns_text": "A=new\nB=value", "value_mode": "按列配置值", "conflict_mode": "覆盖已有字段"},
        )
        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["new", "value"]])
        self.assertEqual(message, "新建列完成：新增 1 列，覆盖 1 列，跳过 0 列；字段：A, B")

    def test_current_datetime_column(self):
        dt = datetime(2026, 6, 15, 9, 8, 7, 123456)
        self.assertEqual(
            render_current_datetime_template(dt, {"template": "{YYYY}-{MM}-{DD} {HH}:{mm}:{ss}.{fff}"}),
            "2026-06-15 09:08:07.123",
        )
        headers, rows, message = apply_current_datetime_column_node(
            ["A"],
            [["x"], ["y"]],
            {"new_field": "Now", "template": "{YYYY}{MM}{DD}"},
            now_func=lambda: dt,
        )
        self.assertEqual(headers, ["A", "Now"])
        self.assertEqual(rows, [["x", "20260615"], ["y", "20260615"]])
        self.assertEqual(message, "新建日期时间列完成：字段【Now】，写入 2 行，示例：20260615")


if __name__ == "__main__":
    unittest.main()
