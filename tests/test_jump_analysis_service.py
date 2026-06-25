# -*- coding: utf-8 -*-
import unittest

from engine.headless import HeadlessWorkflowEngine
from engine.stdio_worker import StdioWorker


def request(action, payload=None, request_id="req1"):
    return {
        "request_id": request_id,
        "api_version": "1.0",
        "action": action,
        "payload": payload or {},
    }


class JumpAnalysisServiceTests(unittest.TestCase):
    def test_analyzes_node_type_id_plan_and_normalizes_issues(self):
        engine = HeadlessWorkflowEngine()
        plan = {
            "nodes": [
                {"node_type_id": "core.condition_check", "enabled": True, "config": {"flag_name": "ok"}},
                {"node_type_id": "core.conditional_jump", "enabled": True, "config": {
                    "flag_name": "ok",
                    "jump_rules": [{"value": "TRUE", "target_anchor_id": "END"}],
                }},
                {"node_type_id": "core.jump_anchor", "enabled": True, "config": {"anchor_id": "END"}},
            ]
        }

        analysis = engine.analyze_jumps(plan)
        manager_state = engine.describe_jump_manager_state(plan)
        validation = engine.validate_jumps(plan)

        self.assertTrue(analysis["ok"])
        self.assertEqual(analysis["anchors"][0]["anchor_id"], "END")
        self.assertEqual(analysis["relations"][0]["target_anchor_id"], "END")
        self.assertEqual(manager_state["schema_version"], "jump_manager_state.v1")
        self.assertEqual(manager_state["layout"]["schema_version"], "jump_manager_layout.v1")
        self.assertEqual(manager_state["ui_hints"]["schema_version"], "jump_manager_ui_hints.v1")
        self.assertEqual(manager_state["actions"]["action_order"], ["refresh", "validate", "format_issue"])
        self.assertEqual(manager_state["counts"]["anchors"], 1)
        self.assertEqual(manager_state["counts"]["relations"], 1)
        self.assertEqual(manager_state["anchors"][0]["reference_count"], 1)
        self.assertEqual(manager_state["anchors"][0]["status"], "active")
        self.assertTrue(validation["ok"])
        self.assertGreaterEqual(validation["counts"]["warning"], 1)
        self.assertEqual(validation["issues"][0]["code"], "jump_validation_warning")

    def test_reports_jump_errors_as_shared_issues(self):
        engine = HeadlessWorkflowEngine()
        plan = {
            "nodes": [
                {"node_type_id": "core.jump_anchor", "config": {"anchor_id": "DUP"}},
                {"node_type_id": "core.jump_anchor", "config": {"anchor_id": "DUP"}},
                {"node_type_id": "core.unconditional_jump", "config": {"target_anchor_id": "MISSING"}},
            ]
        }

        result = engine.validate_jumps(plan)

        self.assertFalse(result["ok"])
        self.assertTrue(any(issue["severity"] == "error" for issue in result["issues"]))
        self.assertTrue(any(issue.get("source") == "JumpAnalysisService" for issue in result["issues"]))
        self.assertIn("跳转校验完成", result["summary"])

    def test_stdio_worker_exposes_jump_actions(self):
        worker = StdioWorker()
        plan = {
            "nodes": [
                {"type": "无条件跳转节点", "config": {"target_anchor_id": ""}},
            ]
        }

        analyzed = worker.handle_request(request("analyze_jumps", {"plan": plan}))
        manager_state = worker.handle_request(request("describe_jump_manager_state", {"plan": plan}))
        validated = worker.handle_request(request("validate_jumps", {"plan": plan}))
        formatted = worker.handle_request(request("format_jump_issue", {
            "issue": validated["result"]["issues"][0],
        }))

        self.assertTrue(analyzed["ok"])
        self.assertTrue(manager_state["ok"])
        self.assertEqual(manager_state["result"]["schema_version"], "jump_manager_state.v1")
        self.assertEqual(manager_state["result"]["layout"]["sections"][1]["section_id"], "relations")
        self.assertTrue(validated["ok"])
        self.assertTrue(validated["result"]["ok"])
        self.assertIn("跳转目标锚点未配置", formatted["result"]["text"])


if __name__ == "__main__":
    unittest.main()
