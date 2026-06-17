# -*- coding: utf-8 -*-
import unittest

from workflow.node_dispatch import apply_workflow_node


class NodeDispatchTests(unittest.TestCase):
    def test_dispatch_plain_data_node(self):
        class Window:
            pass

        result = apply_workflow_node(
            Window(),
            ["A"],
            [["a"]],
            {"type": "新建列", "config": {"columns_text": "B=b", "value_mode": "按列配置值"}},
        )

        self.assertEqual(result[0], ["A", "B"])
        self.assertEqual(result[1], [["a", "b"]])
        self.assertIn("新建列完成", result[2])

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

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["Raw"],
            [["abc"]],
            {
                "type": "数据提取",
                "config": {
                    "source_field": "Raw",
                    "method": "正则提取",
                    "regex_pattern": r"(a)",
                    "regex_group": "1",
                    "new_field": "Out",
                },
            },
        )
        self.assertEqual(headers, ["Raw", "Out"])
        self.assertEqual(rows, [["abc", "a"]])
        self.assertEqual(stat, "写入 1 行，跳过 0 行")

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["Raw"],
            [["2026-06-15"]],
            {
                "type": "格式规范化 / 日期时间解析",
                "config": {
                    "source_field": "Raw",
                    "parse_type": "日期",
                    "input_structure": "自动识别常见格式",
                    "output_mode": "覆盖源字段",
                    "output_template": "{YYYY}-{MM}-{DD}",
                    "output_status": False,
                },
            },
        )
        self.assertEqual(headers, ["Raw"])
        self.assertEqual(rows, [["2026-06-15"]])
        self.assertEqual(stat, "格式规范化完成：写入 1 行，失败 0 行，跳过 0 行")

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["A"],
            [["x"]],
            {"type": "新建列", "config": {"columns_text": "B=1", "value_mode": "按列配置值"}},
        )
        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["x", "1"]])
        self.assertIn("新建列完成", stat)

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["A"],
            [["x"]],
            {"type": "新建日期时间列", "config": {"new_field": "Now"}},
        )
        self.assertEqual(headers, ["A", "Now"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "x")
        self.assertTrue(rows[0][1])
        self.assertIn("新建日期时间列完成：字段【Now】", stat)

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["A", "B"],
            [["x", "y"]],
            {"type": "批量更改列名", "config": {"mode": "手动映射改名", "mappings": [{"old": "A", "new": "AA"}]}},
        )
        self.assertEqual(headers, ["AA", "B"])
        self.assertEqual(rows, [["x", "y"]])
        self.assertEqual(stat, "已更改 1 个字段名")

    def test_dispatch_unknown_node_raises(self):
        with self.assertRaisesRegex(ValueError, "未知节点类型：不存在"):
            apply_workflow_node(None, [], [], {"type": "不存在", "config": {}})


if __name__ == "__main__":
    unittest.main()
