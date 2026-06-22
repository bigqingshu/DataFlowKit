# -*- coding: utf-8 -*-
import unittest

from engine import HeadlessWorkflowEngine
from engine.stdio_worker import StdioWorker
from workflow.plan_commands import apply_plan_command


def node_id_counter(prefix="n"):
    count = {"value": 0}

    def make_id():
        count["value"] += 1
        return f"{prefix}{count['value']}"

    return make_id


def request(action, payload=None):
    return {
        "request_id": "req1",
        "api_version": "1.0",
        "action": action,
        "payload": payload or {},
    }


class PlanCommandTests(unittest.TestCase):
    def test_insert_node_creates_default_protocol_node_without_mutating_input(self):
        plan = {"nodes": [{"node_id": "old", "node_type_id": "core.replace", "config": {}}]}

        result = apply_plan_command(
            plan,
            {"type": "insert_node", "node_type_id": "core.new_columns", "after_index": 0, "include_legacy_type": False},
            preview_headers=["A"],
            node_id_factory=node_id_counter(),
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["changed"])
        self.assertEqual(result["selected_index"], 1)
        self.assertEqual(len(plan["nodes"]), 1)
        node = result["plan"]["nodes"][1]
        self.assertEqual(node["node_id"], "n1")
        self.assertEqual(node["node_type_id"], "core.new_columns")
        self.assertNotIn("type", node)
        self.assertIn("columns_text", node["config"])

    def test_delete_move_duplicate_toggle_replace_and_clear_nodes(self):
        plan = {
            "nodes": [
                {"node_id": "a", "node_type_id": "core.new_columns", "name": "A", "enabled": True, "config": {}},
                {"node_id": "b", "node_type_id": "core.replace", "name": "B", "enabled": True, "config": {}},
                {"node_id": "c", "node_type_id": "core.delete_rows", "name": "C", "enabled": True, "config": {}},
            ]
        }

        deleted = apply_plan_command(plan, {"type": "delete_nodes", "indexes": [0, 2]}, node_id_factory=node_id_counter())
        moved = apply_plan_command(plan, {"type": "move_node", "index": 2, "direction": "up"}, node_id_factory=node_id_counter())
        duplicated = apply_plan_command(plan, {"type": "duplicate_node", "index": 1}, node_id_factory=node_id_counter("copy"))
        toggled = apply_plan_command(plan, {"type": "toggle_node_enabled", "index": 1}, node_id_factory=node_id_counter())
        replaced = apply_plan_command(plan, {
            "type": "replace_node",
            "index": 1,
            "node": {"node_type_id": "core.merge_columns", "config": {}},
        }, node_id_factory=node_id_counter("r"))
        cleared = apply_plan_command(plan, {"type": "clear_nodes"}, node_id_factory=node_id_counter())

        self.assertEqual([node["node_id"] for node in deleted["plan"]["nodes"]], ["b"])
        self.assertEqual(deleted["selected_index"], 0)
        self.assertEqual([node["node_id"] for node in moved["plan"]["nodes"]], ["a", "c", "b"])
        self.assertEqual(moved["selected_index"], 1)
        self.assertEqual(duplicated["plan"]["nodes"][2]["node_id"], "copy1")
        self.assertEqual(duplicated["plan"]["nodes"][2]["name"], "B_复制")
        self.assertFalse(toggled["plan"]["nodes"][1]["enabled"])
        self.assertEqual(replaced["plan"]["nodes"][1]["node_id"], "r1")
        self.assertEqual(replaced["plan"]["nodes"][1]["type"], "合并列")
        self.assertEqual(cleared["plan"]["nodes"], [])
        self.assertIsNone(cleared["selected_index"])

    def test_invalid_commands_return_structured_issues(self):
        invalid_plan = apply_plan_command({"nodes": {}}, {"type": "clear_nodes"})
        unknown = apply_plan_command({"nodes": []}, {"type": "not_real"})
        missing_index = apply_plan_command({"nodes": []}, {"type": "delete_nodes"})

        self.assertFalse(invalid_plan["ok"])
        self.assertEqual(invalid_plan["issues"][0]["code"], "invalid_nodes")
        self.assertFalse(unknown["ok"])
        self.assertEqual(unknown["issues"][0]["code"], "unknown_command")
        self.assertFalse(missing_index["ok"])
        self.assertEqual(missing_index["issues"][0]["code"], "missing_index")

    def test_engine_and_stdio_expose_plan_command_service(self):
        engine = HeadlessWorkflowEngine(node_id_factory=node_id_counter("e"))
        worker = StdioWorker(HeadlessWorkflowEngine(node_id_factory=node_id_counter("s")))

        engine_result = engine.apply_plan_command({"nodes": []}, {
            "type": "insert_node",
            "node_type_id": "core.replace",
        })
        worker_response = worker.handle_request(request("apply_plan_command", {
            "plan": {"nodes": []},
            "command": {"type": "insert_node", "node_type_id": "core.new_columns"},
        }))

        self.assertTrue(engine_result["ok"])
        self.assertEqual(engine_result["plan"]["nodes"][0]["node_id"], "e1")
        self.assertEqual(engine_result["plan"]["nodes"][0]["type"], "批量替换")
        self.assertTrue(worker_response["ok"])
        self.assertEqual(worker_response["result"]["plan"]["nodes"][0]["node_id"], "s1")
        self.assertEqual(worker_response["result"]["plan"]["nodes"][0]["node_type_id"], "core.new_columns")


if __name__ == "__main__":
    unittest.main()
