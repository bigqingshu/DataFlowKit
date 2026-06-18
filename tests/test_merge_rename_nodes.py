# -*- coding: utf-8 -*-
import threading
import unittest

from workflow.nodes import data_nodes
from workflow.nodes.merge_rename_nodes import apply_merge_node, apply_rename_columns_node


class MergeRenameNodesTests(unittest.TestCase):
    def test_data_nodes_keeps_merge_rename_compat_exports(self):
        self.assertIs(data_nodes.apply_merge_node, apply_merge_node)
        self.assertIs(data_nodes.apply_rename_columns_node, apply_rename_columns_node)

    def test_merge_node_separators_and_cancel_callback(self):
        headers, rows, message = apply_merge_node(
            ["A", "B", "C"],
            [[" left ", "", "right"], ["", "mid", "end"]],
            {
                "fields": ["A", "B", "C"],
                "separators": ["-", "|"],
                "output_field": "Merged",
                "skip_empty": True,
                "trim_value": True,
            },
        )
        self.assertEqual(headers, ["A", "B", "C", "Merged"])
        self.assertEqual(rows, [[" left ", "", "right", "left-right"], ["", "mid", "end", "mid|end"]])
        self.assertEqual(message, "新增字段 Merged")

        cancel_event = threading.Event()
        cancel_event.set()
        with self.assertRaisesRegex(RuntimeError, "用户取消"):
            apply_merge_node(
                ["A", "B"],
                [["a", "b"]],
                {"fields": ["A", "B"]},
                context={
                    "check_cancelled": lambda _index: (
                        (_ for _ in ()).throw(RuntimeError("用户取消")) if cancel_event.is_set() else None
                    )
                },
            )

    def test_rename_columns_node_warns_dedupes_and_errors(self):
        headers, rows, message = apply_rename_columns_node(
            ["A", "B", "C"],
            [["a", "b", "c"]],
            {
                "mode": "手动映射改名",
                "mappings": [
                    {"old": "A", "new": " X "},
                    {"old": "B", "new": "X"},
                    {"old": "Missing", "new": "Y"},
                ],
                "trim_names": True,
                "duplicate_policy": "自动追加编号",
                "missing_policy": "跳过并记录警告",
            },
        )
        self.assertEqual(headers, ["X", "X_2", "C"])
        self.assertEqual(rows, [["a", "b", "c"]])
        self.assertEqual(message, "已更改 2 个字段名，警告 1 项")

        with self.assertRaisesRegex(ValueError, "字段名重复：X"):
            apply_rename_columns_node(
                ["A", "B"],
                [["a", "b"]],
                {
                    "mode": "手动映射改名",
                    "mappings": [{"old": "A", "new": "X"}, {"old": "B", "new": "X"}],
                    "duplicate_policy": "报错并停止",
                },
            )


if __name__ == "__main__":
    unittest.main()
