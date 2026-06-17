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


if __name__ == "__main__":
    unittest.main()
