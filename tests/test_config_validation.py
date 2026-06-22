# -*- coding: utf-8 -*-
import unittest

from engine import HeadlessWorkflowEngine
from engine.stdio_worker import StdioWorker
from workflow.config_validation import validate_node_config, validate_plan_configs


def request(action, payload=None, request_id="req1"):
    return {
        "request_id": request_id,
        "api_version": "1.0",
        "action": action,
        "payload": payload or {},
    }


class ConfigValidationTests(unittest.TestCase):
    def test_new_columns_and_replace_validation(self):
        ok = validate_node_config(
            "core.new_columns",
            {"columns_text": "B=b", "value_mode": "按列配置值"},
            headers=["A"],
        )
        empty = validate_node_config("core.new_columns", {"columns_text": ""}, headers=["A"])
        duplicate = validate_node_config(
            "core.new_columns",
            {"columns_text": "A=x", "conflict_mode": "存在则报错"},
            headers=["A"],
        )
        replace = validate_node_config(
            "core.replace",
            {"target_field": "Missing", "match_mode": "正则匹配", "match_value": "["},
            headers=["A"],
        )

        self.assertTrue(ok["ok"])
        self.assertFalse(empty["ok"])
        self.assertEqual(empty["issues"][0]["code"], "invalid_new_columns")
        self.assertFalse(duplicate["ok"])
        self.assertEqual(duplicate["issues"][0]["code"], "new_column_exists")
        self.assertFalse(replace["ok"])
        self.assertIn("unknown_target_field", [issue["code"] for issue in replace["issues"]])
        self.assertIn("invalid_regex", [issue["code"] for issue in replace["issues"]])

    def test_merge_and_filter_validation(self):
        merge = validate_node_config(
            "core.merge_columns",
            {"fields": ["A", "Missing"], "output_field": ""},
            headers=["A"],
        )
        filter_result = validate_node_config(
            "core.filter",
            {
                "conditions": [{"field": "Missing", "op": "包含", "value": "x"}],
                "selected_tables": ["T"],
                "join_rules": [{"left": "当前表.A", "op": "??", "right": "T.id"}],
            },
            headers=["A"],
            table_names=["T"],
            table_columns={"T": ["id"]},
        )

        self.assertFalse(merge["ok"])
        self.assertEqual(merge["issues"][0]["code"], "unknown_merge_fields")
        self.assertFalse(filter_result["ok"])
        self.assertIn("unknown_filter_field", [issue["code"] for issue in filter_result["issues"]])
        self.assertIn("invalid_filter_join_op", [issue["code"] for issue in filter_result["issues"]])

    def test_plan_config_validation_adds_node_paths(self):
        result = validate_plan_configs({
            "headers": ["A"],
            "nodes": [
                {"node_type_id": "core.replace", "config": {"target_field": "Missing"}},
            ],
        })

        self.assertFalse(result["ok"])
        self.assertEqual(result["node_count"], 1)
        self.assertEqual(result["issues"][0]["node_index"], 0)
        self.assertTrue(result["issues"][0]["path"].startswith("/nodes/0/config"))

    def test_headless_and_stdio_expose_config_validation(self):
        engine = HeadlessWorkflowEngine()
        worker = StdioWorker(engine)

        direct = engine.validate_config(
            "core.replace",
            {"target_field": "Missing"},
            preview_headers=["A"],
        )
        response = worker.handle_request(request("validate_config", {
            "node_type_id": "core.replace",
            "config": {"target_field": "Missing"},
            "preview_headers": ["A"],
        }))
        plan_response = worker.handle_request(request("validate_plan_configs", {
            "plan": {"headers": ["A"], "nodes": [{"node_type_id": "core.replace", "config": {"target_field": "Missing"}}]},
        }))

        self.assertFalse(direct["ok"])
        self.assertTrue(response["ok"])
        self.assertFalse(response["result"]["ok"])
        self.assertTrue(plan_response["ok"])
        self.assertFalse(plan_response["result"]["ok"])


if __name__ == "__main__":
    unittest.main()
