# -*- coding: utf-8 -*-
import json
import unittest
from pathlib import Path

from engine import HeadlessWorkflowEngine
from engine.stdio_worker import StdioWorker
from workflow.plan_migration import migrate_plan


ROOT = Path(__file__).resolve().parents[1]


def node_id_counter(prefix="n"):
    count = {"value": 0}

    def make_id():
        count["value"] += 1
        return f"{prefix}{count['value']}"

    return make_id


def walk_nodes(nodes):
    for node in nodes:
        yield node
        config = node.get("config") if isinstance(node, dict) else None
        child_nodes = config.get("nodes") if isinstance(config, dict) else None
        if isinstance(child_nodes, list):
            yield from walk_nodes(child_nodes)


def request(action, payload=None):
    return {
        "request_id": "req1",
        "api_version": "1.0",
        "action": action,
        "payload": payload or {},
    }


class PlanMigrationTests(unittest.TestCase):
    def test_migrates_legacy_nodes_without_mutating_input(self):
        original = {
            "template_type": "workflow_plan",
            "version": "1.0",
            "plan_name": "demo",
            "legacy_field": "preserved",
            "nodes": [
                {"type": "新建列", "name": "添加字段", "config": {"columns_text": "B=b"}},
                {"type": "插件节点", "config": {"plugin_id": "word_excel_read_to_db_v1"}},
            ],
        }

        result = migrate_plan(original, node_id_factory=node_id_counter())
        migrated = result["plan"]

        self.assertTrue(result["ok"])
        self.assertTrue(result["changed"])
        self.assertEqual(original["nodes"][0].get("node_id"), None)
        self.assertEqual(migrated["legacy_field"], "preserved")
        self.assertEqual(migrated["nodes"][0]["node_id"], "n1")
        self.assertEqual(migrated["nodes"][0]["node_type_id"], "core.new_columns")
        self.assertEqual(migrated["nodes"][0]["node_version"], "1.0.0")
        self.assertEqual(migrated["nodes"][0]["type"], "新建列")
        self.assertTrue(migrated["nodes"][0]["enabled"])
        self.assertEqual(migrated["nodes"][1]["node_type_id"], "plugin.word_excel_read_to_db_v1")
        self.assertEqual(result["summary"]["node_type_ids_added"], 2)
        self.assertEqual(result["summary"]["node_ids_added"], 2)

    def test_plugin_ids_are_not_double_prefixed(self):
        plan = {"nodes": [{"type": "插件节点", "config": {"plugin_id": "plugin.demo"}}]}

        result = migrate_plan(plan, node_id_factory=node_id_counter())

        self.assertTrue(result["ok"])
        self.assertEqual(result["plan"]["nodes"][0]["node_type_id"], "plugin.demo")

    def test_migrates_nested_group_nodes(self):
        plan = {
            "nodes": [
                {
                    "type": "节点组 / 子工作流",
                    "config": {
                        "group_name": "组",
                        "nodes": [
                            {"type": "批量替换", "config": {"target_field": "A"}},
                        ],
                    },
                }
            ],
        }

        result = migrate_plan(plan, node_id_factory=node_id_counter())
        group = result["plan"]["nodes"][0]
        child = group["config"]["nodes"][0]

        self.assertTrue(result["ok"])
        self.assertEqual(group["node_type_id"], "core.group")
        self.assertEqual(child["node_id"], "n2")
        self.assertEqual(child["node_type_id"], "core.replace")
        self.assertEqual(result["summary"]["nested_nodes_seen"], 1)

    def test_reports_invalid_plan_shapes(self):
        invalid_plan = migrate_plan({"nodes": {"bad": True}})
        invalid_node = migrate_plan({"nodes": ["not a node"]})

        self.assertFalse(invalid_plan["ok"])
        self.assertEqual(invalid_plan["issues"][0]["code"], "invalid_nodes")
        self.assertFalse(invalid_node["ok"])
        self.assertEqual(invalid_node["issues"][0]["code"], "invalid_node")

    def test_engine_and_stdio_expose_migration_service(self):
        engine = HeadlessWorkflowEngine(node_id_factory=node_id_counter("e"))
        worker = StdioWorker(HeadlessWorkflowEngine(node_id_factory=node_id_counter("s")))

        engine_result = engine.migrate_plan({"nodes": [{"type": "新建列", "config": {}}]})
        worker_response = worker.handle_request(request("migrate_plan", {
            "plan": {"nodes": [{"node_type_id": "core.replace", "config": {}}]},
        }))

        self.assertEqual(engine_result["plan"]["nodes"][0]["node_id"], "e1")
        self.assertEqual(engine_result["plan"]["nodes"][0]["node_type_id"], "core.new_columns")
        self.assertTrue(worker_response["ok"])
        self.assertEqual(worker_response["result"]["plan"]["nodes"][0]["node_id"], "s1")
        self.assertEqual(worker_response["result"]["plan"]["nodes"][0]["type"], "批量替换")

    def test_repository_plan_templates_can_be_migrated_read_only(self):
        plan_dir = ROOT / "plan"
        paths = sorted(plan_dir.glob("*.json"))[:3]
        self.assertTrue(paths)

        for path in paths:
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                result = migrate_plan(data, node_id_factory=node_id_counter(path.stem + "_"))

                self.assertTrue(result["ok"])
                for node in walk_nodes(result["plan"].get("nodes", [])):
                    self.assertIn("node_id", node)
                    self.assertIn("node_type_id", node)
                    self.assertIn("node_version", node)


if __name__ == "__main__":
    unittest.main()
