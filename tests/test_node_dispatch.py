# -*- coding: utf-8 -*-
import unittest

from workflow.node_dispatch import apply_workflow_node


class NodeDispatchTests(unittest.TestCase):
    def test_dispatch_plain_data_node(self):
        calls = []

        class Window:
            def apply_new_columns_node(self, headers, rows, config):
                calls.append(("new_columns", tuple(headers), tuple(config.items())))
                return list(headers) + ["B"], [list(row) + ["b"] for row in rows], "new"

        result = apply_workflow_node(
            Window(),
            ["A"],
            [["a"]],
            {"type": "新建列", "config": {"name": "B"}},
        )

        self.assertEqual(result, (["A", "B"], [["a", "b"]], "new"))
        self.assertEqual(calls, [("new_columns", ("A",), (("name", "B"),))])

    def test_dispatch_context_node(self):
        calls = []
        context = {"transit_tables": {}}

        class Window:
            def apply_dedupe_node(self, headers, rows, config, context=None):
                calls.append((config, context))
                return list(headers), [list(row) for row in rows], "dedupe"

        result = apply_workflow_node(
            Window(),
            ["A"],
            [["a"]],
            {"type": "去重 / 重复数据处理", "config": {"fields": ["A"]}},
            context=context,
        )

        self.assertEqual(result[2], "dedupe")
        self.assertIs(calls[0][1], context)

    def test_dispatch_execute_action_node(self):
        calls = []
        context = {}

        class Window:
            def apply_plugin_node(self, headers, rows, config, context=None, execute_actions=False):
                calls.append((config, context, execute_actions))
                return list(headers), [list(row) for row in rows], "plugin"

        result = apply_workflow_node(
            Window(),
            ["A"],
            [["a"]],
            {"type": "插件节点", "config": {"plugin_id": "p1"}},
            execute_actions=True,
            context=context,
        )

        self.assertEqual(result[2], "plugin")
        self.assertEqual(calls, [({"plugin_id": "p1"}, context, True)])

    def test_dispatch_loop_node_drops_control_payload(self):
        class Window:
            def apply_loop_start_node(self, headers, rows, config, context=None):
                return list(headers), [list(row) for row in rows], "loop", {"no_pending": True}

        result = apply_workflow_node(
            Window(),
            ["A"],
            [["a"]],
            {"type": "循环执行起点", "config": {"loop_id": "L"}},
            context={},
        )

        self.assertEqual(result, (["A"], [["a"]], "loop"))

    def test_dispatch_direct_pure_data_nodes_without_window_methods(self):
        class Window:
            pass

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["A"],
            [[" x "], [""]],
            {
                "type": "复制列",
                "config": {
                    "source_field": "A",
                    "new_field": "B",
                    "trim_value": True,
                    "empty_default": "空",
                },
            },
        )

        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [[" x ", "x"], ["", "空"]])
        self.assertEqual(stat, "复制列为新字段 B")

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["A"],
            [["a1"], ["a2"]],
            {"type": "复制行", "config": {"source_row": "2", "insert_mode": "表尾"}},
        )
        self.assertEqual(rows, [["a1"], ["a2"], ["a2"]])
        self.assertEqual(stat, "复制第 2 行 1 次")

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["A", "B", "C"],
            [["a", "b", "c"]],
            {"type": "删除列", "config": {"fields": ["B"]}},
        )
        self.assertEqual((headers, rows, stat), (["A", "C"], [["a", "c"]], "删除 1 列"))

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["A", "B"],
            [["a1", "b1"], ["a2", "b2"]],
            {"type": "删除行", "config": {"delete_mode": "按行号列表", "row_spec": "1"}},
        )
        self.assertEqual((headers, rows, stat), (["A", "B"], [["a2", "b2"]], "删除 1 行"))

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["A", "B", "C"],
            [["a", "b", "c"]],
            {"type": "移动列", "config": {"order": ["C", "A"]}},
        )
        self.assertEqual((headers, rows, stat), (["C", "A", "B"], [["c", "a", "b"]], "已调整列顺序"))

    def test_dispatch_unknown_node_raises(self):
        with self.assertRaisesRegex(ValueError, "未知节点类型：不存在"):
            apply_workflow_node(None, [], [], {"type": "不存在", "config": {}})


if __name__ == "__main__":
    unittest.main()
