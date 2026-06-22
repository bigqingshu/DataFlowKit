# -*- coding: utf-8 -*-
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"


def load_schema(name):
    with (SCHEMA_DIR / name).open("r", encoding="utf-8") as stream:
        return json.load(stream)


class WorkflowProtocolSchemaTests(unittest.TestCase):
    def test_all_protocol_schema_files_are_valid_json_objects(self):
        expected = [
            "workflow_plan.schema.json",
            "workflow_node.schema.json",
            "table_data.schema.json",
            "runtime_message.schema.json",
            "plugin_manifest.schema.json",
        ]

        for name in expected:
            with self.subTest(name=name):
                schema = load_schema(name)
                self.assertIsInstance(schema, dict)
                self.assertEqual(schema.get("$schema"), "http://json-schema.org/draft-07/schema#")
                self.assertIn("$id", schema)
                self.assertIn("title", schema)

    def test_workflow_plan_schema_keeps_existing_templates_valid(self):
        schema = load_schema("workflow_plan.schema.json")

        self.assertEqual(
            schema["required"],
            ["template_type", "version", "plan_name", "nodes"],
        )
        self.assertEqual(schema["properties"]["template_type"]["const"], "workflow_plan")
        self.assertTrue(schema.get("additionalProperties"))
        self.assertIn("workflow_node.schema.json", schema["properties"]["nodes"]["items"]["$ref"])
        self.assertEqual(schema["properties"]["db_path"]["type"], "string")
        self.assertEqual(schema["properties"]["output_path"]["type"], "string")

        sample = {
            "template_type": "workflow_plan",
            "version": "1.0",
            "plan_name": "demo",
            "nodes": [],
            "db_path": "",
            "output_path": "",
            "legacy_field": "preserved",
        }
        for field in schema["required"]:
            self.assertIn(field, sample)

    def test_workflow_node_schema_accepts_old_type_or_new_node_type_id(self):
        schema = load_schema("workflow_node.schema.json")

        self.assertEqual(schema["required"], ["enabled", "config"])
        self.assertTrue(schema.get("additionalProperties"))
        self.assertEqual(schema["properties"]["node_type_id"]["pattern"], "^[A-Za-z0-9_.:-]+$")
        self.assertEqual(schema["anyOf"], [{"required": ["type"]}, {"required": ["node_type_id"]}])

        old_style = {
            "type": "新建列",
            "enabled": True,
            "config": {},
        }
        new_style = {
            "node_type_id": "core.new_columns",
            "enabled": True,
            "config": {},
        }
        for sample in (old_style, new_style):
            self.assertIn("enabled", sample)
            self.assertIn("config", sample)
            self.assertTrue("type" in sample or "node_type_id" in sample)

    def test_table_data_schema_allows_json_scalar_cells_and_extensions(self):
        schema = load_schema("table_data.schema.json")
        row_item_type = schema["properties"]["rows"]["items"]["items"]["type"]

        self.assertEqual(schema["required"], ["type", "headers", "rows"])
        self.assertEqual(schema["properties"]["type"]["const"], "table")
        self.assertEqual(row_item_type, ["string", "number", "integer", "boolean", "null"])
        self.assertTrue(schema.get("additionalProperties"))

        sample = {
            "type": "table",
            "headers": ["A", "B"],
            "rows": [["x", 1], [None, True]],
            "metadata": {},
            "extensions": {"client": "test"},
        }
        self.assertEqual(sample["type"], "table")
        self.assertEqual(len(sample["headers"]), 2)

    def test_runtime_message_schema_matches_planned_worker_actions_and_events(self):
        schema = load_schema("runtime_message.schema.json")
        defs = schema["definitions"]
        actions = defs["request"]["properties"]["action"]["enum"]
        event_types = defs["event"]["properties"]["type"]["enum"]

        for action in [
            "list_node_types",
            "get_node_type",
            "list_node_ui_schemas",
            "get_node_ui_schema",
            "migrate_plan",
            "list_plan_templates",
            "load_plan_template",
            "save_plan_template",
            "validate_plan_template",
            "apply_plan_command",
            "validate_config",
            "validate_plan_configs",
            "make_default_node",
            "validate_plan",
            "preview_plan",
            "start_job",
            "run_plan",
            "cancel_job",
            "get_job_status",
            "get_job_events",
            "list_output_modes",
            "apply_output",
            "list_tables",
            "load_table",
            "get_table_page",
            "list_plugins",
        ]:
            self.assertIn(action, actions)

        for event_type in [
            "workflow_start",
            "workflow_done",
            "workflow_cancelled",
            "job_started",
            "job_done",
            "job_failed",
            "job_cancel_requested",
            "node_start",
            "node_done",
            "node_error",
        ]:
            self.assertIn(event_type, event_types)

        self.assertEqual(defs["request"]["required"], ["request_id", "api_version", "action", "payload"])
        self.assertEqual(defs["response"]["required"], ["request_id", "ok"])

    def test_plugin_manifest_schema_keeps_current_manifest_shapes(self):
        schema = load_schema("plugin_manifest.schema.json")
        defs = schema["definitions"]
        parameter_schema = defs["parameterSchema"]

        self.assertTrue(schema.get("additionalProperties"))
        self.assertIn("^(plugin_info|PLUGIN_INFO|info)$", schema["patternProperties"])
        self.assertEqual(
            schema["patternProperties"]["^(plugin_info|PLUGIN_INFO|info)$"]["$ref"],
            "#/definitions/pluginInfo",
        )
        self.assertEqual(defs["pluginInfo"]["required"], ["id", "api_version"])
        self.assertEqual(parameter_schema["type"], "array")
        self.assertEqual(parameter_schema["items"]["required"], ["name", "type"])


if __name__ == "__main__":
    unittest.main()
