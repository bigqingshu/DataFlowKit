# -*- coding: utf-8 -*-
import os
import tempfile
import unittest
from pathlib import Path

from engine.headless import HeadlessWorkflowEngine
from engine.plugin_service import PluginService
from engine.stdio_worker import StdioWorker


def request(action, payload=None, request_id="req1"):
    return {
        "request_id": request_id,
        "api_version": "1.0",
        "action": action,
        "payload": payload or {},
    }


def write_demo_plugin(root):
    plugin = Path(root) / "demo_plugin.py"
    plugin.write_text(
        "\n".join([
            "PLUGIN_INFO = {'id': 'demo', 'name': 'Demo', 'api_version': '1.0', 'version': '0.1', 'description': 'Demo plugin'}",
            "PARAMETER_SCHEMA = [",
            "    {'name': 'field', 'label': '字段', 'type': 'field_select', 'default': 'A', 'required': True},",
            "    {'name': 'limit', 'label': '数量', 'type': 'int', 'default': 3},",
            "]",
            "def run(input_data, params, context):",
            "    return {'ok': True, 'output': input_data}",
        ]),
        encoding="utf-8",
    )
    return plugin


class PluginServiceTests(unittest.TestCase):
    def test_lists_plugins_and_builds_json_safe_schema(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            write_demo_plugin(temp_dir)
            service = PluginService(plugins_dir=temp_dir, app_dir=temp_dir)

            listed = service.list_plugins()
            schema = service.get_plugin_schema("plugin.demo")
            default_config = service.make_plugin_default_config("demo")
            node = service.make_default_plugin_node("plugin.demo", node_id="node_demo", include_legacy_type=False)
            run = service.run_plugin(
                "demo",
                input_table={"headers": ["A"], "rows": [["x"]]},
                params={"field": "A", "limit": 1},
            )

        self.assertTrue(listed["ok"])
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["plugins"][0]["plugin_id"], "demo")
        self.assertNotIn("module", listed["plugins"][0])
        self.assertEqual(listed["display_map"]["插件 / Demo"], "demo")
        self.assertTrue(schema["ok"])
        self.assertEqual(schema["schema"]["node_type_id"], "plugin.demo")
        self.assertEqual(schema["schema"]["display_name"], "插件 / Demo")
        self.assertEqual(schema["schema"]["parameters"][0]["name"], "field")
        self.assertEqual(default_config["params"], {"field": "A", "limit": 3})
        self.assertTrue(default_config["external_env_dir"].endswith(os.path.join("plugin_envs", "demo")))
        self.assertEqual(node["node_type_id"], "plugin.demo")
        self.assertNotIn("type", node)
        self.assertEqual(node["config"]["plugin_id"], "demo")
        self.assertTrue(run["ok"])
        self.assertEqual(run["result"]["headers"], ["A"])
        self.assertEqual(run["result"]["rows"], [["x"]])

    def test_headless_catalog_and_plan_command_include_plugins(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            write_demo_plugin(temp_dir)
            engine = HeadlessWorkflowEngine(node_id_factory=lambda: "node_test")
            engine.plugins = PluginService(plugins_dir=temp_dir, app_dir=temp_dir)

            catalog = engine.list_node_catalog(include_unsupported=True)
            schemas = engine.list_node_ui_schemas(include_unsupported=True)
            node_schema = engine.get_node_type("plugin.demo")
            made = engine.make_default_node("plugin.demo", include_legacy_type=False)
            command = engine.apply_plan_command(
                {"nodes": []},
                {"type": "insert_node", "node_type_id": "plugin.demo", "include_legacy_type": False},
            )
            result = engine.preview_plan({
                "nodes": [{
                    "node_type_id": "plugin.demo",
                    "config": {"plugin_id": "demo", "params": {}},
                }],
                "headers": ["A"],
                "rows": [["x"]],
            })

        self.assertIn("plugin.demo", [item["node_type_id"] for item in catalog])
        self.assertTrue([item for item in catalog if item["node_type_id"] == "plugin.demo"][0]["supported_headless"])
        self.assertIn("plugin.demo", [item["node_type_id"] for item in schemas])
        self.assertEqual(node_schema["default_config"]["params"]["field"], "A")
        self.assertTrue(node_schema["supported"])
        self.assertEqual(made["config"]["plugin_id"], "demo")
        self.assertTrue(command["ok"])
        inserted = command["plan"]["nodes"][0]
        self.assertEqual(inserted["node_type_id"], "plugin.demo")
        self.assertEqual(inserted["config"]["params"]["limit"], 3)
        self.assertEqual(result.headers, ["A"])
        self.assertEqual(result.rows, [["x"]])
        self.assertIn("插件 Demo 完成", result.logs[0])

    def test_stdio_worker_exposes_plugin_service_actions(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            write_demo_plugin(temp_dir)
            worker = StdioWorker()

            listed = worker.handle_request(request("list_plugins", {"plugins_dir": temp_dir}))
            schema = worker.handle_request(request("get_plugin_schema", {
                "plugin_id": "plugin.demo",
                "plugins_dir": temp_dir,
            }))
            default_config = worker.handle_request(request("make_plugin_default_config", {
                "plugin_id": "demo",
                "plugins_dir": temp_dir,
            }))
            run = worker.handle_request(request("run_plugin", {
                "plugin_id": "demo",
                "plugins_dir": temp_dir,
                "input_table": {"headers": ["A"], "rows": [["x"]]},
                "params": {"field": "A", "limit": 1},
            }))

        self.assertTrue(listed["ok"])
        self.assertEqual(listed["result"]["plugins"][0]["node_type_id"], "plugin.demo")
        self.assertTrue(schema["ok"])
        self.assertEqual(schema["result"]["schema"]["display_name"], "插件 / Demo")
        self.assertTrue(default_config["ok"])
        self.assertEqual(default_config["result"]["config"]["params"]["field"], "A")
        self.assertTrue(run["ok"])
        self.assertEqual(run["result"]["result"]["headers"], ["A"])

    def test_missing_plugin_schema_returns_issue(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            service = PluginService(plugins_dir=temp_dir, app_dir=temp_dir)
            result = service.get_plugin_schema("plugin.missing")

        self.assertFalse(result["ok"])
        self.assertEqual(result["issues"][0]["code"], "plugin_not_found")


if __name__ == "__main__":
    unittest.main()
