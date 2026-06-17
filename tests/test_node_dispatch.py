# -*- coding: utf-8 -*-
import os
import tempfile
import types
import unittest
from unittest import mock

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
        progress = []
        calls = []

        class Window:
            def check_workflow_cancelled(self, context=None):
                return None

            def report_workflow_node_progress(self, context=None, current=None, total=None, message="", node_name=""):
                progress.append((context, current, total, message, node_name))

            def apply_batch_rename_node(self, headers, rows, config, execute_actions=False, context=None):
                calls.append((config, execute_actions, context))
                return list(headers), [list(row) for row in rows], "rename"

        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "a.txt"), "w", encoding="utf-8") as f:
                f.write("a")

            window = Window()
            window.app = types.SimpleNamespace(app_dir=tmp)
            result = apply_workflow_node(
                window,
                ["A"],
                [["a"]],
                {"type": "获取文件列表", "config": {"recursive": False}},
                context={"progress_callback": lambda item: None},
            )

            self.assertEqual(result[0][0], "文件名")
            self.assertEqual(result[1][0][0], "a.txt")
            self.assertIn("读取文件列表 1 项", result[2])

            rename_result = apply_workflow_node(
                window,
                ["完整路径", "新文件名"],
                [[os.path.join(tmp, "a.txt"), "b.txt"]],
                {"type": "批量重命名", "config": {"actual_rename": False}},
            )

        self.assertEqual(rename_result[2], "重命名预览：可处理 1 项，跳过/失败 0 项")
        self.assertEqual(calls, [])

    def test_dispatch_execute_action_node(self):
        context = {}
        expected = (["A"], [["plugin"]], "plugin runtime")

        class Window:
            def apply_plugin_node(self, headers, rows, config, context=None, execute_actions=False):
                raise AssertionError("should dispatch to plugin runtime helper")

        with mock.patch("workflow.node_dispatch.apply_plugin_node_for_window", return_value=expected) as helper:
            result = apply_workflow_node(
                Window(),
                ["A"],
                [["a"]],
                {"type": "插件节点", "config": {"plugin_id": "p1"}},
                execute_actions=True,
                context=context,
            )

        self.assertEqual(result, expected)
        self.assertEqual(helper.call_args.args[:4], (mock.ANY, ["A"], [["a"]], {"plugin_id": "p1"}))
        self.assertTrue(helper.call_args.kwargs["execute_actions"])
        self.assertIs(helper.call_args.kwargs["context"], context)

    def test_dispatch_output_nodes_use_runtime_helpers(self):
        class Window:
            def apply_save_transit_node(self, *_args, **_kwargs):
                raise AssertionError("should dispatch to output runtime helper")

            def apply_selected_columns_write_node(self, *_args, **_kwargs):
                raise AssertionError("should dispatch to output runtime helper")

            def apply_writeback_node(self, *_args, **_kwargs):
                raise AssertionError("should dispatch to output runtime helper")

        helper_results = {
            "save": (["A"], [["save"]], "save runtime"),
            "selected": (["A"], [["selected"]], "selected runtime"),
            "writeback": (["A"], [["writeback"]], "writeback runtime"),
        }
        with mock.patch(
            "workflow.node_dispatch.apply_save_transit_node_for_window",
            return_value=helper_results["save"],
        ) as save_helper, mock.patch(
            "workflow.node_dispatch.apply_selected_columns_write_node_for_window",
            return_value=helper_results["selected"],
        ) as selected_helper, mock.patch(
            "workflow.node_dispatch.apply_writeback_node_for_window",
            return_value=helper_results["writeback"],
        ) as writeback_helper:
            context = {"transit_tables": {}}
            self.assertEqual(
                apply_workflow_node(
                    Window(),
                    ["A"],
                    [["x"]],
                    {"type": "保存中转数据", "config": {"transit_name": "T"}},
                    execute_actions=True,
                    context=context,
                ),
                helper_results["save"],
            )
            self.assertEqual(
                apply_workflow_node(
                    Window(),
                    ["A"],
                    [["x"]],
                    {"type": "选定列写入指定表", "config": {"target_type": "当前工作表"}},
                    execute_actions=True,
                    context=context,
                ),
                helper_results["selected"],
            )
            self.assertEqual(
                apply_workflow_node(
                    Window(),
                    ["A"],
                    [["x"]],
                    {"type": "字段映射写入表", "config": {"target_table": "T"}},
                    execute_actions=True,
                    context=context,
                ),
                helper_results["writeback"],
            )

        self.assertEqual(save_helper.call_args.args[:4], (mock.ANY, ["A"], [["x"]], {"transit_name": "T"}))
        self.assertTrue(save_helper.call_args.kwargs["execute_actions"])
        self.assertIs(save_helper.call_args.kwargs["context"], context)
        self.assertEqual(selected_helper.call_args.args[:4], (mock.ANY, ["A"], [["x"]], {"target_type": "当前工作表"}))
        self.assertEqual(writeback_helper.call_args.args[:4], (mock.ANY, ["A"], [["x"]], {"target_table": "T"}))

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
            MAX_EXPANDED_ROWS = 200000
            MAX_TARGET_CELLS = 1000000

            def check_workflow_cancelled_periodically(self, context, index):
                return None

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

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["A", "B"],
            [["x", "y"]],
            {"type": "合并列", "config": {"fields": ["A", "B"], "separators": ["-"], "output_field": "AB"}},
        )
        self.assertEqual(headers, ["A", "B", "AB"])
        self.assertEqual(rows, [["x", "y", "x-y"]])
        self.assertEqual(stat, "新增字段 AB")

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["A"],
            [["x"], ["x"], ["y"]],
            {"type": "去重 / 重复数据处理", "config": {"key_fields": ["A"]}},
        )
        self.assertEqual(headers, ["A", "重复组编号", "重复状态", "组内序号", "重复次数", "是否保留"])
        self.assertEqual(len(rows), 2)
        self.assertIn("去重完成", stat)

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["A"],
            [["2"]],
            {
                "type": "列数字运算",
                "config": {
                    "target_field": "A",
                    "operation": "乘",
                    "operand_source": "固定值",
                    "operand_value": "3",
                    "output_mode": "生成新字段",
                    "output_field": "Result",
                },
            },
        )
        self.assertEqual(headers, ["A", "Result"])
        self.assertEqual(rows, [["2", "6"]])
        self.assertIn("列数字运算完成：成功 1 行", stat)

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["Text"],
            [["abc"]],
            {
                "type": "批量替换",
                "config": {
                    "target_field": "Text",
                    "match_mode": "正则匹配",
                    "replace_mode": "局部替换匹配字符串",
                    "match_value": "abc",
                    "replace_value": "x",
                },
            },
        )
        self.assertEqual(rows, [["x"]])
        self.assertIn("修改 1 处", stat)

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["A"],
            [["", ""], ["x", ""]],
            {
                "type": "填充值",
                "config": {
                    "target_field": "A",
                    "value_source": "手动输入值",
                    "manual_value": "v",
                    "direction": "向下",
                    "end_mode": "固定数量",
                    "count": "2",
                    "overwrite_rule": "只填充空单元格",
                },
            },
        )
        self.assertEqual(rows[0][0], "v")
        self.assertEqual(stat, "填充 1 个单元格，跳过 1 个")

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["Seq"],
            [[""], [""]],
            {
                "type": "序列填充",
                "config": {
                    "target_field": "Seq",
                    "start_value": "1",
                    "step": "1",
                    "direction": "向下",
                    "end_mode": "固定数量",
                    "count": "2",
                    "overwrite_rule": "覆盖所有目标单元格",
                },
            },
        )
        self.assertEqual(rows, [["1"], ["2"]])
        self.assertEqual(stat, "序列填充 2 个单元格，跳过 0 个")

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["A", "B"],
            [["", ""], ["", ""]],
            {
                "type": "区域填充",
                "config": {
                    "start_field": "A",
                    "end_field": "B",
                    "start_row": "1",
                    "end_row": "2",
                    "value_source": "手动输入值",
                    "manual_value": "v",
                    "overwrite_rule": "覆盖所有目标单元格",
                },
            },
        )
        self.assertEqual(rows, [["v", "v"], ["v", "v"]])
        self.assertEqual(stat, "区域填充 4 个单元格，跳过 0 个")

        headers, rows, stat = apply_workflow_node(
            Window(),
            ["ID", "A"],
            [["R1", "x"], ["R2", "y"]],
            {
                "type": "行数据映射填充",
                "config": {
                    "keep_fields": ["ID"],
                    "value_fields": ["A"],
                    "start_row": "1",
                },
            },
        )
        self.assertEqual(headers, ["ID", "原始行号", "来源字段", "输出内容", "状态"])
        self.assertEqual(len(rows), 2)
        self.assertIn("按行取值展开", stat)

    def test_dispatch_match_value_output_prepares_lookup_context(self):
        class Window:
            MAX_EXPANDED_ROWS = 200000
            MAX_TARGET_CELLS = 1000000

            def check_workflow_cancelled_periodically(self, context, index):
                return None

            def load_lookup_table_for_match_value_output(self, config, context=None):
                self.loaded = (config, context)
                return ["Needle"], [{"__row_index__": 1, "Needle": "x"}]

        context = {"transit_tables": {}}
        window = Window()
        headers, rows, stat = apply_workflow_node(
            window,
            ["Source"],
            [["x"]],
            {
                "type": "匹配值输出列名",
                "config": {
                    "source_field": "Source",
                    "lookup_table": "lookup",
                    "lookup_fields": ["Needle"],
                    "output_match_value": False,
                    "output_match_row": False,
                    "output_status": False,
                },
            },
            context=context,
        )

        self.assertIs(window.loaded[1], context)
        self.assertEqual(headers, ["Source", "匹配字段名"])
        self.assertEqual(rows, [["x", "Needle"]])
        self.assertIn("匹配值输出列名完成：成功 1 行", stat)

    def test_dispatch_unknown_node_raises(self):
        with self.assertRaisesRegex(ValueError, "未知节点类型：不存在"):
            apply_workflow_node(None, [], [], {"type": "不存在", "config": {}})


if __name__ == "__main__":
    unittest.main()
