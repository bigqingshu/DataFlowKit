# -*- coding: utf-8 -*-
import os
import sqlite3
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


def write_external_plugin(root, *, with_db_request=False):
    plugin = Path(root) / "external_plugin.py"
    run_body = [
        "def run(input_data, params, context):",
        "    headers = list(input_data.get('headers') or []) + ['External']",
        "    rows = [list(row) + ['yes'] for row in (input_data.get('rows') or [])]",
        "    result = {'ok': True, 'output': {'headers': headers, 'rows': rows}, 'message': 'external ok', 'logs': [{'level': 'INFO', 'message': 'ran external'}]}",
    ]
    if with_db_request:
        run_body.extend([
            "    result['database_requests'] = [{'operation': 'write_table', 'table_name': 'external_out', 'headers': ['A'], 'rows': [['db']], 'mode': 'replace'}]",
        ])
    run_body.extend([
        "    return result",
    ])
    plugin.write_text(
        "\n".join([
            "import argparse",
            "import json",
            "PLUGIN_INFO = {'id': 'external_demo', 'name': 'External Demo', 'api_version': '1.0', 'version': '0.1', 'description': 'External plugin', 'run_mode': 'external_python'}",
            "PARAMETER_SCHEMA = []",
            *run_body,
            "def _main():",
            "    parser = argparse.ArgumentParser()",
            "    parser.add_argument('--input', required=True)",
            "    parser.add_argument('--output', required=True)",
            "    args = parser.parse_args()",
            "    with open(args.input, 'r', encoding='utf-8') as f:",
            "        payload = json.load(f)",
            "    result = run(payload.get('input_data') or {}, payload.get('params') or {}, payload.get('context') or {})",
            "    with open(args.output, 'w', encoding='utf-8') as f:",
            "        json.dump(result, f, ensure_ascii=False)",
            "if __name__ == '__main__':",
            "    _main()",
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
        plugin_param_group = next(group for group in schema["schema"]["form"]["groups"] if group["title"] == "插件参数")
        plugin_param_fields = {field["key"]: field for field in plugin_param_group["fields"]}
        self.assertEqual(plugin_param_fields["params.field"]["config_path"], ["params", "field"])
        self.assertEqual(plugin_param_fields["params.field"]["options_source"], {"type": "preview_headers"})
        self.assertEqual(plugin_param_fields["params.field"]["action"]["key"], "pick_preview_header")
        self.assertEqual(plugin_param_fields["params.limit"]["config_path"], ["params", "limit"])
        self.assertEqual(plugin_param_fields["params.limit"]["type"], "number")
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

    def test_external_process_plugin_runs_through_service(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            entry = write_external_plugin(temp_dir)
            service = PluginService(plugins_dir=temp_dir, app_dir=temp_dir)

            catalog = service.list_plugin_node_catalog()
            schema = service.get_plugin_schema("plugin.external_demo")
            run = service.run_plugin(
                "external_demo",
                input_table={"headers": ["A"], "rows": [["x"]]},
                config={
                    "plugin_id": "external_demo",
                    "run_mode": "插件独立环境",
                    "external_entry": str(entry),
                    "params": {},
                },
            )

        item = [p for p in catalog["plugins"] if p["plugin_id"] == "external_demo"][0]
        self.assertTrue(item["supported_headless"])
        self.assertEqual(schema["schema"]["capabilities"]["headless_run"], True)
        self.assertTrue(run["ok"])
        self.assertEqual(run["result"]["headers"], ["A", "External"])
        self.assertEqual(run["result"]["rows"], [["x", "yes"]])
        self.assertIn("ran external", [log.get("message") for log in run["result"]["logs"]])

    def test_external_process_database_requests_use_service_db_path(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            entry = write_external_plugin(temp_dir, with_db_request=True)
            db_path = str(Path(temp_dir) / "external.db")
            service = PluginService(plugins_dir=temp_dir, app_dir=temp_dir, db_path=db_path)

            preview = service.run_plugin(
                "external_demo",
                input_table={"headers": ["A"], "rows": [["x"]]},
                config={"plugin_id": "external_demo", "run_mode": "插件独立环境", "external_entry": str(entry)},
                execute_actions=False,
            )
            preview_created_db = os.path.exists(db_path)
            executed = service.run_plugin(
                "external_demo",
                input_table={"headers": ["A"], "rows": [["x"]]},
                config={"plugin_id": "external_demo", "run_mode": "插件独立环境", "external_entry": str(entry)},
                execute_actions=True,
            )
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute('SELECT "A" FROM "external_out"').fetchall()
            finally:
                conn.close()

        self.assertTrue(preview["ok"])
        self.assertFalse(preview_created_db)
        self.assertTrue(executed["ok"])
        self.assertEqual(rows, [("db",)])

    def test_missing_plugin_schema_returns_issue(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            service = PluginService(plugins_dir=temp_dir, app_dir=temp_dir)
            result = service.get_plugin_schema("plugin.missing")

        self.assertFalse(result["ok"])
        self.assertEqual(result["issues"][0]["code"], "plugin_not_found")


if __name__ == "__main__":
    unittest.main()
