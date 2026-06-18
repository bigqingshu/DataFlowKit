# -*- coding: utf-8 -*-
import threading
import unittest

from workflow.nodes import data_nodes
from workflow.nodes.replace_nodes import (
    apply_replace_node,
    replace_pair_count_for_row,
    replace_row_index_for_policy,
    replace_source_value,
)


class ReplaceNodesTests(unittest.TestCase):
    def test_data_nodes_keeps_replace_compat_exports(self):
        self.assertIs(data_nodes.apply_replace_node, apply_replace_node)
        self.assertIs(data_nodes.replace_pair_count_for_row, replace_pair_count_for_row)
        self.assertIs(data_nodes.replace_row_index_for_policy, replace_row_index_for_policy)
        self.assertIs(data_nodes.replace_source_value, replace_source_value)

    def test_manual_and_column_replace(self):
        headers, rows, message = apply_replace_node(
            ["Text"],
            [["abc abc"], ["ABC"]],
            {
                "target_field": "Text",
                "match_mode": "包含",
                "replace_mode": "局部替换匹配字符串",
                "match_value": "abc",
                "replace_value": "x",
                "replace_count": "1",
            },
        )
        self.assertEqual(headers, ["Text"])
        self.assertEqual(rows, [["x abc"], ["ABC"]])
        self.assertEqual(message, "修改 1 处")

        _headers, rows, message = apply_replace_node(
            ["Text", "Match", "Replace"],
            [["red apple", "red", "green"], ["blue berry", "berry", "bird"]],
            {
                "target_field": "Text",
                "match_value_source": "列字段",
                "match_value_field": "Match",
                "replace_value_source": "列字段",
                "replace_value_field": "Replace",
                "match_row_policy": "当前行",
                "replace_row_policy": "当前行",
                "match_mode": "包含",
            },
        )
        self.assertEqual(rows, [["green apple", "red", "green"], ["blue bird", "berry", "bird"]])
        self.assertEqual(message, "修改 2 处")

    def test_invalid_regex_and_cancel_callback(self):
        with self.assertRaisesRegex(ValueError, "批量替换正则错误"):
            apply_replace_node(
                ["Text"],
                [["abc"]],
                {"target_field": "Text", "match_mode": "正则匹配", "match_value": "(", "replace_value": "x"},
            )

        cancel_event = threading.Event()
        cancel_event.set()
        with self.assertRaisesRegex(RuntimeError, "用户取消"):
            apply_replace_node(
                ["Text"],
                [["abc"]],
                {"target_field": "Text", "match_mode": "包含", "match_value": "a", "replace_value": "x"},
                context={
                    "check_cancelled": lambda _index: (
                        (_ for _ in ()).throw(RuntimeError("用户取消")) if cancel_event.is_set() else None
                    )
                },
            )


if __name__ == "__main__":
    unittest.main()
