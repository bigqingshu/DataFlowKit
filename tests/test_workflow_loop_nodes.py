# -*- coding: utf-8 -*-
import unittest

from DataFlowKit import PlanWorkflowWindow
from workflow.nodes.loop_nodes import (
    apply_loop_judge_to_state,
    build_loop_judge_output,
    build_loop_start_output,
    evaluate_loop_condition,
    find_loop_judge_index,
    find_loop_start_index,
    init_loop_state_from_source,
    loop_last_non_empty_row_index,
    take_next_loop_item,
)


class WorkflowLoopNodesTests(unittest.TestCase):
    def test_init_loop_state_respects_boundary_flags_and_selected_fields(self):
        state = init_loop_state_from_source(
            ["执行标志", "名称", "参考"],
            [["", "A", "x"], ["1", "B", "y"], ["2", "C", ""]],
            "当前表",
            {
                "loop_id": "L",
                "fields": ["名称"],
                "boundary_mode": "指定参考列数据边界",
                "reference_field": "参考",
                "running_flag_policy": "执行中1重置为0",
                "current_table_name": "当前项",
            },
        )

        self.assertEqual(state["queue_headers"], ["执行标志", "原始行号", "名称"])
        self.assertEqual(state["queue_rows"], [["0", "1", "A"], ["0", "2", "B"]])
        self.assertEqual(state["current_table_name"], "当前项")
        self.assertEqual(loop_last_non_empty_row_index(["A"], [["x"], [""]], "A"), 0)

    def test_take_next_loop_item_and_output_modes(self):
        state = init_loop_state_from_source(["A"], [["a"], ["b"]], "当前表", {"loop_id": "L"})

        first = take_next_loop_item(state)

        self.assertFalse(first["no_pending"])
        self.assertEqual(first["current_headers"], ["A"])
        self.assertEqual(first["current_row"], ["a"])
        self.assertEqual(state["queue_rows"][0][0], "1")
        self.assertEqual(state["current_index"], 0)
        self.assertEqual(
            build_loop_start_output(["原"], [["x"]], first, output_current_as_table=True),
            (["A"], [["a"]], "循环 L 取第 1 条，标志 0→1", {"no_pending": False}),
        )
        self.assertEqual(
            build_loop_start_output(["原"], [["x"]], first, output_current_as_table=False),
            (["原"], [["x"]], "循环 L 取第 1 条，标志 0→1，当前表保持不变", {"no_pending": False}),
        )

        state["queue_rows"][1][0] = "2"
        state["queue_rows"][0][0] = "2"
        empty = take_next_loop_item(state)
        self.assertTrue(empty["no_pending"])
        self.assertEqual(empty["transit_rows"], [])

    def test_evaluate_loop_condition_supports_current_item_and_regex(self):
        state = init_loop_state_from_source(["名称"], [["Alpha"]], "当前表", {"loop_id": "L"})
        take_next_loop_item(state)

        self.assertEqual(evaluate_loop_condition([], [], {"condition_mode": "始终成功"}), (True, "始终成功"))
        self.assertEqual(evaluate_loop_condition([], [["r"]], {"condition_mode": "结果表行数>0"}), (True, "当前结果行数=1"))
        self.assertEqual(
            evaluate_loop_condition(
                [],
                [],
                {
                    "condition_source": "当前循环项表",
                    "condition_mode": "字段包含",
                    "condition_field": "名称",
                    "condition_value": "ph",
                },
                loop_state=state,
            ),
            (True, "名称=Alpha"),
        )
        self.assertEqual(
            evaluate_loop_condition(["A"], [["abc"]], {"condition_mode": "正则匹配", "condition_field": "A", "condition_value": "["})[0],
            False,
        )

    def test_apply_loop_judge_updates_state_and_builds_final_output(self):
        state = init_loop_state_from_source(["A"], [["a"], ["b"]], "当前表", {"loop_id": "L"})
        take_next_loop_item(state)

        judge = apply_loop_judge_to_state(["R"], [["ok"]], {"loop_id": "L", "condition_mode": "始终成功"}, state, now_text="2026-01-01")

        self.assertEqual(state["queue_rows"][0][0], "2")
        self.assertIsNone(state["current_index"])
        self.assertTrue(judge["has_pending"])
        self.assertEqual(judge["result_row"], ["L", "1", "1", "满足", "完成2", "始终成功", "2026-01-01"])
        self.assertEqual(
            build_loop_judge_output(["R"], [["ok"]], {"loop_id": "L"}, state, judge, [judge["result_row"]]),
            (["R"], [["ok"]], "循环 L 完成2，仍有待执行项，准备回跳", {"jump_to": "__LOOP_START__"}),
        )

        state["queue_rows"][1][0] = "2"
        judge["has_pending"] = False
        self.assertEqual(
            build_loop_judge_output(["R"], [["ok"]], {"loop_id": "L", "end_output_mode": "循环结果表"}, state, judge, [judge["result_row"]]),
            (["循环名称", "循环序号", "队列行号", "判断结果", "标记状态", "说明", "时间"], [judge["result_row"]], "循环 L 已全部结束，输出循环结果表", {"jump_to": None}),
        )

    def test_find_loop_indexes(self):
        nodes = [
            {"type": "循环执行起点", "config": {"loop_id": "A"}},
            {"type": "循环判断回跳", "config": {"loop_id": "B"}},
            {"type": "循环判断回跳", "config": {"loop_id": "A"}},
        ]

        self.assertEqual(find_loop_start_index("A", 2, nodes), 0)
        self.assertEqual(find_loop_judge_index("A", 0, 2, nodes), 2)
        self.assertIsNone(find_loop_start_index("B", 1, nodes))

    def test_dataflowkit_loop_nodes_write_transit_tables(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        events = []
        window.check_transit_table_write_permission = lambda *args, **kwargs: {"ok": True}
        window.log_transit_table_event = lambda manager, action, name, headers, rows, **kwargs: events.append((action, name, headers, rows, kwargs))
        context = {}

        headers, rows, stat, ctrl = window.apply_loop_start_node(
            ["A"],
            [["a"], ["b"]],
            {"loop_id": "L", "fields": ["A"], "current_table_name": "当前项"},
            context=context,
        )

        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["a"]])
        self.assertEqual(ctrl, {"no_pending": False})
        self.assertIn("当前项", context["transit_tables"])
        self.assertIn("取第 1 条", stat)

        headers, rows, stat, ctrl = window.apply_loop_judge_node(
            headers,
            rows,
            {"loop_id": "L", "condition_mode": "始终成功", "result_table_name": "循环结果"},
            context=context,
        )

        self.assertEqual(ctrl, {"jump_to": "__LOOP_START__"})
        self.assertIn("循环结果", context["transit_tables"])
        self.assertIn("循环队列_L", context["transit_tables"])
        self.assertEqual(context["loop_states"]["L"]["queue_rows"][0][0], "2")
        self.assertTrue(any(event[1] == "循环结果" for event in events))


if __name__ == "__main__":
    unittest.main()
