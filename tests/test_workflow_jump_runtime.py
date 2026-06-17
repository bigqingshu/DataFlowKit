# -*- coding: utf-8 -*-
import unittest
from datetime import datetime

from DataFlowKit import PlanWorkflowWindow
from workflow.jump_runtime import append_jump_runtime_log


class JumpRuntimeTests(unittest.TestCase):
    def test_append_jump_runtime_log_enriches_current_node_info(self):
        context = {
            "current_node_info": {
                "node_id": "n1",
                "node_name": "跳转",
                "node_type": "无条件跳转节点",
                "node_index": 3,
            }
        }

        payload = append_jump_runtime_log(
            context,
            {"event": "test", "status": "ok"},
            now_factory=lambda: datetime(2026, 6, 17, 9, 30, 1),
        )

        self.assertEqual(payload["time"], "2026-06-17 09:30:01")
        self.assertEqual(payload["node_id"], "n1")
        self.assertEqual(payload["node_index"], 3)
        self.assertEqual(context["jump_logs"], [payload])
        self.assertIsNone(append_jump_runtime_log(None, {"event": "skip"}))

    def test_dataflowkit_jump_anchor_node_logs_and_keeps_table(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        context = {}

        headers, rows, stat = window.apply_jump_anchor_node(
            ["A"],
            [["a"]],
            {"anchor_id": "A1", "anchor_name": "开始"},
            context=context,
        )

        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["a"]])
        self.assertEqual(stat, "定位锚点：A1 / 开始")
        self.assertEqual(context["jump_logs"][0]["event"], "anchor")
        self.assertEqual(context["jump_logs"][0]["anchor_id"], "A1")

    def test_dataflowkit_resolve_jump_target_control_logs_success_and_warning(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)

        def fake_resolve(anchor_id, anchors_info=None, nodes=None):
            if anchor_id == "ok":
                return 2, "OK"
            return None, f"目标锚点不存在：{anchor_id}"

        window.resolve_jump_anchor_index = fake_resolve
        context = {}

        ctrl = window.resolve_jump_target_control("ok", context=context, source="jump")
        missing = window.resolve_jump_target_control("missing", context=context, source="jump")

        self.assertEqual(ctrl, {"jump_to": 2, "message": "跳转到锚点 ok（节点 3）", "status": "ok"})
        self.assertEqual(missing["jump_to"], None)
        self.assertEqual(missing["status"], "warning")
        self.assertEqual([item["status"] for item in context["jump_logs"]], ["ok", "warning"])

    def test_dataflowkit_unconditional_jump_node_returns_control_payload(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        window.resolve_jump_anchor_index = lambda anchor_id, anchors_info=None, nodes=None: (1, "OK")
        context = {}

        headers, rows, stat, ctrl = window.apply_unconditional_jump_node(
            ["A"],
            [["a"]],
            {"target_anchor_id": "target"},
            context=context,
        )

        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["a"]])
        self.assertEqual(ctrl["jump_to"], 1)
        self.assertIn("无条件跳转：跳转到锚点 target（节点 2）", stat)
        self.assertEqual(context["jump_logs"][0]["event"], "unconditional_jump")

    def test_dataflowkit_condition_check_evaluates_counts_and_writes_flag(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        context = {"current_node_info": {"node_name": "条件判断"}}

        self.assertEqual(window.condition_count_empty_cells(["A"], [[""], ["x"]], "A"), 1)
        self.assertEqual(window.condition_count_contains_cells(["A"], [["Alpha"], ["beta"]], "A", "a", case_sensitive=False), 2)
        passed, actual, detail = window.evaluate_condition_check_node(
            ["A"],
            [[""], ["x"]],
            {"condition_type": "字段空值数量", "field": "A", "op": "等于", "value": "1"},
        )

        self.assertTrue(passed)
        self.assertEqual(actual, 1)
        self.assertIn("字段空值数量：A=1", detail)

        headers, rows, stat = window.apply_condition_check_node(
            ["A"],
            [["yes"], ["no"]],
            {
                "flag_name": "flag",
                "condition_type": "字段值",
                "field": "A",
                "op": "等于",
                "value": "yes",
                "true_value": "Y",
                "false_value": "N",
            },
            context=context,
        )

        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["yes"], ["no"]])
        self.assertIn("条件判断：flag=Y", stat)
        self.assertEqual(context["condition_flags"]["flag"]["value"], "Y")
        self.assertEqual(context["jump_logs"][-1]["event"], "condition_check")

    def test_dataflowkit_conditional_jump_handles_missing_and_matching_flags(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        window.resolve_jump_anchor_index = lambda anchor_id, anchors_info=None, nodes=None: (4, "OK")
        config = {
            "flag_name": "flag",
            "jump_rules": [{"value": "Y", "target_anchor_id": "target_y"}],
            "default_anchor_id": "default",
        }

        self.assertEqual(window.find_conditional_jump_target("N", config), ("default", "条件值 N 未映射，使用默认锚点"))

        missing_context = {}
        headers, rows, stat, ctrl = window.apply_conditional_jump_node(["A"], [["a"]], config, context=missing_context)
        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["a"]])
        self.assertEqual(ctrl["jump_to"], None)
        self.assertIn("条件标志未产生：flag", stat)
        self.assertEqual(missing_context["jump_logs"][0]["status"], "warning")

        context = {"condition_flags": {"flag": {"value": "Y"}}}
        headers, rows, stat, ctrl = window.apply_conditional_jump_node(["A"], [["a"]], config, context=context)

        self.assertEqual(ctrl, {"jump_to": 4, "message": "跳转到锚点 target_y（节点 5）", "status": "ok"})
        self.assertIn("条件跳转：flag=Y；命中条件值 Y", stat)
        self.assertEqual(context["jump_logs"][0]["event"], "conditional_jump")


if __name__ == "__main__":
    unittest.main()
