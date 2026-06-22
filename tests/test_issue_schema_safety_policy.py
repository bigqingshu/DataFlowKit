# -*- coding: utf-8 -*-
import unittest

from engine import HeadlessWorkflowEngine
from engine.issue_schema import has_error_issues, make_issue, normalize_issue, normalize_issues
from engine.safety_policy import resolve_safety_policy
from engine.stdio_worker import StdioWorker


def request(action, payload=None, request_id="req1"):
    return {
        "request_id": request_id,
        "api_version": "1.0",
        "action": action,
        "payload": payload or {},
    }


class IssueSchemaSafetyPolicyTests(unittest.TestCase):
    def test_issue_schema_normalizes_and_preserves_extensions(self):
        issue = make_issue(
            "WARNING",
            "demo",
            "提示",
            path="/nodes/0",
            node_index=0,
            node_type="新建列",
            node_type_id="core.new_columns",
            suggestion="检查配置",
            source="test",
            extra_value=3,
        )

        self.assertEqual(issue["severity"], "warning")
        self.assertEqual(issue["path"], "/nodes/0")
        self.assertEqual(issue["node_index"], 0)
        self.assertEqual(issue["extra_value"], 3)
        self.assertFalse(has_error_issues([issue]))
        self.assertTrue(has_error_issues([make_issue("error", "bad", "错误")]))
        self.assertEqual(normalize_issue({"code": "x"})["severity"], "error")
        self.assertEqual(normalize_issues(["boom"])[0]["code"], "invalid_issue")

    def test_safety_policy_resolves_preview_dry_run_and_run_modes(self):
        preview = resolve_safety_policy("preview", execute_actions=True)
        dry_run = resolve_safety_policy("run", execute_actions=True, dry_run=True)
        run = resolve_safety_policy("run", execute_actions=True)
        safe_run = resolve_safety_policy("run", execute_actions=False)

        self.assertTrue(preview.preview)
        self.assertFalse(preview.execute_actions)
        self.assertTrue(preview.dry_run)
        self.assertEqual(dry_run.mode, "dry_run")
        self.assertFalse(dry_run.execute_actions)
        self.assertTrue(dry_run.dry_run)
        self.assertTrue(run.execute_actions)
        self.assertFalse(run.dry_run)
        self.assertFalse(safe_run.execute_actions)

    def test_headless_context_carries_effective_safety_policy(self):
        engine = HeadlessWorkflowEngine()
        plan = {
            "nodes": [
                {
                    "node_type_id": "core.new_columns",
                    "config": {"columns_text": "B=b", "value_mode": "按列配置值"},
                }
            ]
        }
        input_table = {"type": "table", "headers": ["A"], "rows": [["a"]]}

        preview = engine.preview_plan(
            plan,
            input_table=input_table,
            initial_context={"execute_actions": True},
        )
        run = engine.run_plan(plan, input_table=input_table, execute_actions=True)
        dry_run = engine.run_plan(plan, input_table=input_table, execute_actions=True, dry_run=True)

        self.assertFalse(preview.context["execute_actions"])
        self.assertTrue(preview.context["dry_run"])
        self.assertEqual(preview.context["safety_policy"]["mode"], "preview")
        self.assertTrue(run.context["execute_actions"])
        self.assertFalse(run.context["dry_run"])
        self.assertEqual(run.context["safety_policy"]["mode"], "run")
        self.assertFalse(dry_run.context["execute_actions"])
        self.assertTrue(dry_run.context["dry_run"])
        self.assertEqual(dry_run.context["safety_policy"]["mode"], "dry_run")

    def test_stdio_run_plan_honors_dry_run_payload(self):
        worker = StdioWorker()
        response = worker.handle_request(request("run_plan", {
            "plan": {
                "nodes": [
                    {
                        "node_type_id": "core.new_columns",
                        "config": {"columns_text": "B=b", "value_mode": "按列配置值"},
                    }
                ]
            },
            "input_data": {"type": "table", "headers": ["A"], "rows": [["a"]]},
            "execute_actions": True,
            "dry_run": True,
        }))

        self.assertTrue(response["ok"])
        context = response["result"]["context"]
        self.assertFalse(context["execute_actions"])
        self.assertTrue(context["dry_run"])
        self.assertEqual(context["safety_policy"]["mode"], "dry_run")


if __name__ == "__main__":
    unittest.main()
