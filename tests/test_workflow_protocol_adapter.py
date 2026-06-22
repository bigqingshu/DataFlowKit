# -*- coding: utf-8 -*-
import unittest

from workflow.protocol_adapter import (
    build_runtime_request,
    build_workflow_plan_payload,
    display_type_for_node,
    stable_node_type_id,
    upgrade_node_for_protocol,
)


class WorkflowProtocolAdapterTests(unittest.TestCase):
    def test_stable_node_type_id_maps_builtin_and_plugin_nodes(self):
        self.assertEqual(stable_node_type_id({"type": "新建列", "config": {}}), "core.new_columns")
        self.assertEqual(
            stable_node_type_id({"type": "插件节点", "config": {"plugin_id": "demo"}}),
            "plugin.demo",
        )
        self.assertEqual(
            display_type_for_node({"node_type_id": "plugin.demo", "config": {"plugin_id": "demo"}}),
            "插件节点",
        )
        self.assertEqual(stable_node_type_id({"node_type_id": "core.new_columns", "config": {}}), "core.new_columns")
        self.assertEqual(display_type_for_node({"node_type_id": "core.new_columns", "config": {}}), "新建列")

    def test_upgrade_node_preserves_config_and_adds_protocol_fields(self):
        calls = []

        def ensure_node_id(node):
            calls.append(node)
            node.setdefault("node_id", f"node_{len(calls)}")

        node = {
            "type": "节点组 / 子工作流",
            "name": "组",
            "config": {
                "nodes": [
                    {"type": "新建列", "enabled": True, "config": {"columns_text": "B"}},
                ]
            },
        }
        upgraded = upgrade_node_for_protocol(node, ensure_node_id=ensure_node_id)

        self.assertEqual(upgraded["node_id"], "node_1")
        self.assertEqual(upgraded["node_type_id"], "core.group")
        self.assertEqual(upgraded["node_version"], "1.0.0")
        self.assertEqual(upgraded["ui"], {})
        self.assertEqual(upgraded["extensions"], {})
        self.assertEqual(upgraded["config"]["nodes"][0]["node_type_id"], "core.new_columns")
        self.assertNotIn("node_type_id", node)

    def test_build_workflow_plan_payload_can_include_input_table(self):
        payload = build_workflow_plan_payload(
            plan_name="demo",
            nodes=[{"type": "新建列", "enabled": True, "config": {"columns_text": "B"}}],
            output_mode="输出到主界面预览区",
            output_table="结果",
            backup_before_overwrite=True,
            table_access_policy="audit",
            headers=["A"],
            rows=[["a"]],
        )

        self.assertEqual(payload["template_type"], "workflow_plan")
        self.assertEqual(payload["version"], "1.0")
        self.assertEqual(payload["nodes"][0]["node_type_id"], "core.new_columns")
        self.assertEqual(payload["headers"], ["A"])
        self.assertEqual(payload["rows"], [["a"]])

    def test_build_runtime_request(self):
        payload = build_runtime_request("r1", "preview_plan", {"x": 1})

        self.assertEqual(payload["request_id"], "r1")
        self.assertEqual(payload["api_version"], "1.0")
        self.assertEqual(payload["action"], "preview_plan")
        self.assertEqual(payload["payload"], {"x": 1})


if __name__ == "__main__":
    unittest.main()
