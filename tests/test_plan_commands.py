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

    def test_update_node_fields_and_patch_node_config(self):
        plan = {
            "nodes": [
                {
                    "node_id": "a",
                    "node_type_id": "core.new_columns",
                    "type": "新建列",
                    "name": "旧名称",
                    "enabled": True,
                    "config": {"columns_text": "B=b", "value_mode": "按列配置值"},
                }
            ]
        }

        updated = apply_plan_command(
            plan,
            {"type": "update_node_fields", "index": 0, "fields": {"name": "新名称", "enabled": False}},
            node_id_factory=node_id_counter(),
        )
        patched = apply_plan_command(
            plan,
            {"type": "patch_node_config", "index": 0, "config": {"columns_text": "C=c", "value_mode": None}},
            node_id_factory=node_id_counter(),
        )

        self.assertTrue(updated["ok"])
        self.assertEqual(updated["plan"]["nodes"][0]["name"], "新名称")
        self.assertFalse(updated["plan"]["nodes"][0]["enabled"])
        self.assertEqual(updated["selected_index"], 0)
        self.assertTrue(patched["ok"])
        self.assertEqual(patched["plan"]["nodes"][0]["config"]["columns_text"], "C=c")
        self.assertNotIn("value_mode", patched["plan"]["nodes"][0]["config"])

    def test_update_config_list_supports_append_update_move_and_delete(self):
        plan = {
            "nodes": [
                {
                    "node_id": "a",
                    "node_type_id": "core.conditional_jump",
                    "type": "条件跳转",
                    "enabled": True,
                    "config": {
                        "flag_name": "flag_a",
                        "jump_rules": [
                            {"value": "A", "target_anchor_id": "ANCHOR_A"},
                            {"value": "B", "target_anchor_id": "ANCHOR_B"},
                        ],
                    },
                }
            ]
        }

        appended = apply_plan_command(
            plan,
            {
                "type": "update_config_list",
                "index": 0,
                "field": "jump_rules",
                "action": "append",
                "item": {"value": "C", "target_anchor_id": "ANCHOR_C"},
            },
            node_id_factory=node_id_counter(),
        )
        updated = apply_plan_command(
            plan,
            {
                "type": "update_config_list",
                "index": 0,
                "field": "jump_rules",
                "action": "update",
                "item_index": 1,
                "item": {"target_anchor_id": "ANCHOR_B2"},
            },
            node_id_factory=node_id_counter(),
        )
        moved = apply_plan_command(
            plan,
            {
                "type": "update_config_list",
                "index": 0,
                "field": "jump_rules",
                "action": "move",
                "item_index": 1,
                "direction": "up",
            },
            node_id_factory=node_id_counter(),
        )
        deleted = apply_plan_command(
            plan,
            {
                "type": "update_config_list",
                "index": 0,
                "field": "jump_rules",
                "action": "delete",
                "item_index": 0,
            },
            node_id_factory=node_id_counter(),
        )

        self.assertTrue(appended["ok"])
        self.assertEqual(len(appended["plan"]["nodes"][0]["config"]["jump_rules"]), 3)
        self.assertEqual(appended["plan"]["nodes"][0]["config"]["jump_rules"][-1]["value"], "C")

        self.assertTrue(updated["ok"])
        self.assertEqual(updated["plan"]["nodes"][0]["config"]["jump_rules"][1]["value"], "B")
        self.assertEqual(updated["plan"]["nodes"][0]["config"]["jump_rules"][1]["target_anchor_id"], "ANCHOR_B2")

        self.assertTrue(moved["ok"])
        moved_rules = moved["plan"]["nodes"][0]["config"]["jump_rules"]
        self.assertEqual(moved_rules[0]["value"], "B")
        self.assertEqual(moved_rules[1]["value"], "A")

        self.assertTrue(deleted["ok"])
        self.assertEqual(len(deleted["plan"]["nodes"][0]["config"]["jump_rules"]), 1)
        self.assertEqual(deleted["plan"]["nodes"][0]["config"]["jump_rules"][0]["value"], "B")

    def test_update_config_list_reports_invalid_shape(self):
        plan = {
            "nodes": [
                {
                    "node_id": "a",
                    "node_type_id": "core.new_columns",
                    "config": {"columns_text": "B=b"},
                }
            ]
        }

        result = apply_plan_command(
            plan,
            {
                "type": "update_config_list",
                "index": 0,
                "field": "columns_text",
                "action": "append",
                "item": "C=c",
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["issues"][0]["code"], "invalid_list_field")

    def test_update_node_fields_rejects_reserved_fields(self):
        plan = {"nodes": [{"node_id": "a", "node_type_id": "core.new_columns", "config": {}}]}

        result = apply_plan_command(
            plan,
            {"type": "update_node_fields", "index": 0, "fields": {"config": {"columns_text": "B=b"}}},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["issues"][0]["code"], "reserved_field_patch")

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

        patch_response = worker.handle_request(request("apply_plan_command", {
            "plan": {
                "nodes": [{
                    "node_id": "n1",
                    "node_type_id": "core.new_columns",
                    "type": "新建列",
                    "name": "节点A",
                    "enabled": True,
                    "config": {"columns_text": "B=b", "value_mode": "按列配置值"},
                }],
            },
            "command": {"type": "patch_node_config", "index": 0, "config": {"columns_text": "C=c"}},
        }))

        self.assertTrue(patch_response["ok"])
        self.assertEqual(patch_response["result"]["plan"]["nodes"][0]["config"]["columns_text"], "C=c")

        list_response = worker.handle_request(request("apply_plan_command", {
            "plan": {
                "nodes": [{
                    "node_id": "n1",
                    "node_type_id": "core.conditional_jump",
                    "type": "条件跳转",
                    "enabled": True,
                    "config": {
                        "flag_name": "flag_a",
                        "jump_rules": [{"value": "A", "target_anchor_id": "ANCHOR_A"}],
                    },
                }],
            },
            "command": {
                "type": "update_config_list",
                "index": 0,
                "field": "jump_rules",
                "action": "append",
                "item": {"value": "B", "target_anchor_id": "ANCHOR_B"},
            },
        }))

        self.assertTrue(list_response["ok"])
        self.assertEqual(len(list_response["result"]["plan"]["nodes"][0]["config"]["jump_rules"]), 2)


if __name__ == "__main__":
    unittest.main()
