# -*- coding: utf-8 -*-
import unittest

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
            def apply_loop_start_node(self, headers, rows, config, context=None):
                return list(headers), [list(row) for row in rows], "loop start", {"no_pending": True}

            def find_loop_judge_index(self, loop_id, idx, end, nodes=None):
                self.seen = (loop_id, idx, end, nodes)
                return 4

        window = Window()
        node_list = [{"type": "x"}] * 6
        headers, rows, stat, jump_to = dispatch_run_plan_node(
            window,
            ["A"],
            [["a"]],
            {"type": "循环执行起点", "config": {"loop_id": "L"}},
            {},
            node_list=node_list,
            idx=1,
            end=5,
        )

        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["a"]])
        self.assertEqual(jump_to, 5)
        self.assertIn("无待执行项，跳过循环体到节点 6", stat)
        self.assertEqual(window.seen, ("L", 1, 5, node_list))

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
