# -*- coding: utf-8 -*-
import unittest
from unittest import mock

from workflow.run_plan_dispatch import dispatch_run_plan_node


class RunPlanDispatchTests(unittest.TestCase):
    def test_dispatch_falls_back_to_apply_node_for_regular_nodes(self):
        class Window:
            def apply_node(self, headers, rows, node, execute_actions=False, context=None):
                return list(headers) + ["B"], [list(row) + ["b"] for row in rows], f"regular:{execute_actions}"

        headers, rows, stat, jump_to = dispatch_run_plan_node(
            Window(),
            ["A"],
            [["a"]],
            {"type": "新建列", "config": {}},
            {},
            execute_actions=True,
        )

        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["a", "b"]])
        self.assertEqual(stat, "regular:True")
        self.assertIsNone(jump_to)

    def test_dispatch_loop_start_can_jump_after_judge_when_no_pending(self):
        class Window:
            def apply_loop_start_node(self, *_args, **_kwargs):
                raise AssertionError("should dispatch to loop runtime helper")

            def find_loop_judge_index(self, loop_id, idx, end, nodes=None):
                self.seen = (loop_id, idx, end, nodes)
                return 4

        window = Window()
        node_list = [{"type": "x"}] * 6
        context = {}
        with mock.patch(
            "workflow.run_plan_dispatch.apply_loop_start_node_for_window",
            return_value=(["A"], [["a"]], "loop start", {"no_pending": True}),
        ) as start_helper:
            headers, rows, stat, jump_to = dispatch_run_plan_node(
                window,
                ["A"],
                [["a"]],
                {"type": "循环执行起点", "config": {"loop_id": "L"}},
                context,
                node_list=node_list,
                idx=1,
                end=5,
            )

        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["a"]])
        self.assertEqual(jump_to, 5)
        self.assertIn("无待执行项，跳过循环体到节点 6", stat)
        self.assertEqual(window.seen, ("L", 1, 5, node_list))
        self.assertEqual(start_helper.call_args.args[:4], (window, ["A"], [["a"]], {"loop_id": "L"}))
        self.assertIs(start_helper.call_args.kwargs["context"], context)

    def test_dispatch_loop_judge_resolves_runtime_loop_start_jump(self):
        class Window:
            def apply_loop_judge_node(self, *_args, **_kwargs):
                raise AssertionError("should dispatch to loop runtime helper")

            def find_loop_start_index(self, loop_id, idx, nodes=None):
                self.seen = (loop_id, idx, nodes)
                return 2

        window = Window()
        node_list = [{"type": "x"}] * 4
        context = {}
        with mock.patch(
            "workflow.run_plan_dispatch.apply_loop_judge_node_for_window",
            return_value=(["A"], [["a"]], "loop judge", {"jump_to": "__LOOP_START__"}),
        ) as judge_helper:
            headers, rows, stat, jump_to = dispatch_run_plan_node(
                window,
                ["A"],
                [["a"]],
                {"type": "循环判断回跳", "config": {"loop_id": "L"}},
                context,
                node_list=node_list,
                idx=3,
            )

        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["a"]])
        self.assertEqual(stat, "loop judge")
        self.assertEqual(jump_to, 2)
        self.assertEqual(window.seen, ("L", 3, node_list))
        self.assertEqual(judge_helper.call_args.args[:4], (window, ["A"], [["a"]], {"loop_id": "L"}))
        self.assertIs(judge_helper.call_args.kwargs["context"], context)

    def test_dispatch_conditional_jump_returns_target(self):
        class Window:
            def apply_conditional_jump_node(self, headers, rows, config, context=None, anchors_info=None, nodes=None):
                self.seen = (context, anchors_info, nodes)
                return list(headers), [list(row) for row in rows], "cond jump", {"jump_to": 3}

        window = Window()
        context = {}
        anchors = {"all": []}
        node_list = [{"type": "条件跳转节点"}]

        headers, rows, stat, jump_to = dispatch_run_plan_node(
            window,
            ["A"],
            [["a"]],
            {"type": "条件跳转节点", "config": {"flag_name": "flag"}},
            context,
            anchors_info=anchors,
            node_list=node_list,
        )

        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["a"]])
        self.assertEqual(stat, "cond jump")
        self.assertEqual(jump_to, 3)
        self.assertEqual(window.seen, (context, anchors, node_list))


if __name__ == "__main__":
    unittest.main()
