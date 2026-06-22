# -*- coding: utf-8 -*-
import os
import sqlite3
import tempfile
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


class AccessPolicyServiceTests(unittest.TestCase):
    def test_builds_default_access_for_node_type_id_without_legacy_type(self):
        engine = HeadlessWorkflowEngine()
        result = engine.build_table_access({
            "node_type_id": "core.new_columns",
            "enabled": True,
            "config": {"columns_text": "B"},
        })

        self.assertTrue(result["ok"])
        self.assertEqual(result["node_type"], "新建列")
        self.assertEqual(result["node_type_id"], "core.new_columns")
        current = result["table_access"]["tables"][0]
        self.assertEqual(current["table"], "__CURRENT_TABLE__")
        self.assertTrue(current["permissions"]["write_table"])
        self.assertTrue(current["log_only"])

    def test_precheck_reports_sqlite_output_issues_and_policy_state(self):
        engine = HeadlessWorkflowEngine()

        audit = engine.precheck_access(
            {"nodes": []},
            execute_actions=True,
            output_mode="保存为SQLite新表",
            output_table="",
            db_path="",
            table_access_policy="audit",
        )
        strict = engine.precheck_access(
            {"nodes": []},
            execute_actions=True,
            output_mode="保存为SQLite新表",
            output_table="",
            db_path="",
            table_access_policy="strict",
        )

        self.assertFalse(audit["ok"])
        self.assertTrue(audit["can_continue"])
        self.assertGreaterEqual(audit["blocking_count"], 1)
        self.assertTrue(all(issue.get("source") == "AccessPolicyService" for issue in audit["issues"]))
        self.assertTrue(any(issue["code"] == "table_access_permission_error" for issue in audit["issues"]))
        self.assertIn("权限预检完成", audit["summary"])
        self.assertFalse(strict["can_continue"])

    def test_precheck_uses_node_type_id_defaults_and_sqlite_table_list(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            db_path = os.path.join(temp_dir, "access.db")
            conn = sqlite3.connect(db_path)
            try:
                conn.execute("CREATE TABLE present (a TEXT)")
                conn.commit()
            finally:
                conn.close()

            engine = HeadlessWorkflowEngine()
            plan = {
                "nodes": [
                    {
                        "node_type_id": "core.filter",
                        "enabled": True,
                        "config": {"extra_tables": ["missing"]},
                    }
                ]
            }

            result = engine.precheck_access(
                plan,
                execute_actions=False,
                db_path=db_path,
                table_access_policy="strict",
            )

        self.assertFalse(result["ok"])
        self.assertFalse(result["can_continue"])
        self.assertEqual(result["issues"][0]["node_type_id"], "core.filter")
        self.assertEqual(result["issues"][0]["path"], "/nodes/0/table_access")
        self.assertTrue(any("SQLite 来源表不存在：missing" in issue["message"] for issue in result["issues"]))

    def test_format_and_audit_helpers_are_ui_free(self):
        engine = HeadlessWorkflowEngine()
        issue = {
            "severity": "warning",
            "message": "需要确认写入范围。",
            "node": "1.写入",
            "table": "out",
            "operation": "写表",
            "suggestion": "确认目标表。",
        }
        text = engine.format_access_issue(issue)
        recorded = engine.record_access_audit({
            "node_name": "写入",
            "table_name": "out",
            "operation": "write_table",
            "status": "warning",
            "message": "demo",
        })
        listed = engine.list_access_audit_logs(selected_status="warning", keyword="demo")

        self.assertIn("需要确认写入范围", text)
        self.assertEqual(recorded["count"], 1)
        self.assertEqual(len(listed["visible"]), 1)
        self.assertIn("warning 1", listed["summary"])

    def test_stdio_worker_exposes_access_policy_actions(self):
        worker = StdioWorker()

        built = worker.handle_request(request("build_table_access", {
            "node": {"node_type_id": "core.new_columns", "enabled": True, "config": {}},
        }))
        checked = worker.handle_request(request("precheck_access", {
            "plan": {"nodes": []},
            "execute_actions": True,
            "output_mode": "保存为SQLite新表",
            "output_table": "",
            "db_path": "",
            "table_access_policy": "strict",
        }))
        formatted = worker.handle_request(request("format_access_issue", {
            "issue": checked["result"]["issues"][0],
        }))
        recorded = worker.handle_request(request("record_access_audit", {
            "event": {"status": "ok", "message": "audit event"},
        }))
        listed = worker.handle_request(request("list_access_audit_logs", {
            "selected_status": "ok",
            "keyword": "audit",
        }))
        audit_text = worker.handle_request(request("format_access_audit_event", {
            "event": recorded["result"]["event"],
        }))

        self.assertTrue(built["ok"])
        self.assertEqual(built["result"]["node_type"], "新建列")
        self.assertTrue(checked["ok"])
        self.assertFalse(checked["result"]["can_continue"])
        self.assertIn("输出方式需要", formatted["result"]["text"])
        self.assertEqual(recorded["result"]["count"], 1)
        self.assertEqual(len(listed["result"]["visible"]), 1)
        self.assertIn("audit event", audit_text["result"]["text"])


if __name__ == "__main__":
    unittest.main()
