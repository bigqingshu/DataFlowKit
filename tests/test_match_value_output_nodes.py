# -*- coding: utf-8 -*-
import unittest

from workflow.nodes.match_value_output_nodes import (
    apply_match_value_output_field_name_node,
    match_value_output_column_match,
)


class MatchValueOutputNodesTests(unittest.TestCase):
    def test_match_modes_handle_case_contains_and_regex(self):
        self.assertTrue(match_value_output_column_match("ABC", "ABC", "完全相等"))
        self.assertTrue(match_value_output_column_match("ABC", "bc", "忽略大小写当前值包含匹配值"))
        self.assertTrue(match_value_output_column_match("abc123", r"\d+", "正则匹配"))
        self.assertFalse(match_value_output_column_match("abc", "(", "正则匹配"))
        self.assertFalse(match_value_output_column_match("abc", "x", "完全相等"))

    def test_node_writes_single_multi_and_no_match_outputs(self):
        lookup_context = {
            "lookup_columns": ["ColA", "ColB"],
            "lookup_records": [
                {"__row_index__": 1, "ColA": "alpha", "ColB": "beta"},
                {"__row_index__": 2, "ColA": "gamma", "ColB": "alpha"},
            ],
        }

        headers, rows, message = apply_match_value_output_field_name_node(
            ["Source"],
            [["beta"], ["alpha"], ["none"]],
            {
                "source_field": "Source",
                "lookup_table": "lookup",
                "lookup_fields": ["ColA", "ColB"],
                "match_mode": "完全相等",
                "multi_match_policy": "合并所有字段名",
                "multi_match_separator": "|",
            },
            context=lookup_context,
        )

        self.assertEqual(headers, ["Source", "匹配字段名", "匹配值", "匹配行号", "匹配状态"])
        self.assertEqual(rows[0], ["beta", "ColB", "beta", "1", "成功"])
        self.assertEqual(rows[1], ["alpha", "ColA|ColB", "alpha", "1|2", "多匹配，共2项"])
        self.assertEqual(rows[2], ["none", "未匹配", "", "", "未匹配"])
        self.assertEqual(message, "匹配值输出列名完成：成功 1 行，多匹配 1 行，未匹配 1 行")

    def test_node_validates_lookup_config_and_cancel_callback(self):
        lookup_context = {"lookup_columns": ["A"], "lookup_records": [{"__row_index__": 1, "A": "x"}]}

        with self.assertRaisesRegex(ValueError, "请选择当前表匹配字段"):
            apply_match_value_output_field_name_node(
                ["Source"],
                [["x"]],
                {"lookup_table": "lookup", "lookup_fields": ["A"]},
                context=lookup_context,
            )
        with self.assertRaisesRegex(ValueError, "匹配表字段不存在：Missing"):
            apply_match_value_output_field_name_node(
                ["Source"],
                [["x"]],
                {"source_field": "Source", "lookup_table": "lookup", "lookup_fields": ["Missing"]},
                context=lookup_context,
            )
        with self.assertRaisesRegex(RuntimeError, "用户取消"):
            apply_match_value_output_field_name_node(
                ["Source"],
                [["x"]],
                {"source_field": "Source", "lookup_table": "lookup", "lookup_fields": ["A"]},
                context={
                    "lookup_columns": ["A"],
                    "lookup_records": [{"__row_index__": 1, "A": "x"}],
                    "check_cancelled": lambda _index: (_ for _ in ()).throw(RuntimeError("用户取消")),
                },
            )


if __name__ == "__main__":
    unittest.main()
