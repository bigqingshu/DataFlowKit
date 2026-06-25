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
            "def open_config_window(parent, current_params, context):",
            "    params = dict(current_params)",
            "    params['limit'] = 9",
            "    params['table_count'] = len(context.get('input_tables') or {})",
            "    params['has_plugin_data_dir'] = bool(context.get('plugin_data_dir'))",
            "    return params",
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


def write_patch_plugin(root):
    plugin = Path(root) / "patch_plugin.py"
    plugin.write_text(
        "\n".join([
            "PLUGIN_INFO = {'id': 'patch_demo', 'name': 'Patch Demo', 'api_version': '1.0'}",
            "PARAMETER_SCHEMA = [{'name': 'mode', 'label': '模式', 'type': 'text', 'default': 'old'}]",
            "def describe_config(params, context):",
            "    return {'schema_version': 'patch_demo.config.v1', 'summary': {'mode': params.get('mode', '')}}",
            "def validate_config_patch(params, context, patch):",
            "    if patch.get('operation') != 'set_param':",
            "        return {'ok': False, 'message': 'unsupported operation'}",
            "    if not patch.get('key'):",
            "        return False, 'missing key'",
            "    return {'ok': True, 'message': 'patch ok'}",
            "def apply_config_patch(params, context, patch):",
            "    params = dict(params)",
            "    params[patch.get('key')] = patch.get('value')",
            "    return {'ok': True, 'params': params, 'changed': True, 'message': 'patched'}",
            "def preview_config_effect(params, context):",
            "    return {'schema_version': 'patch_demo.effect.v1', 'summary': {'mode': params.get('mode', '')}, 'expected_output_fields': ['A']}",
            "def run(input_data, params, context):",
            "    return {'ok': True, 'output': input_data}",
        ]),
        encoding="utf-8",
    )
    return plugin


def write_config_options_plugin(root):
    plugin = Path(root) / "config_options_plugin.py"
    plugin.write_text(
        "\n".join([
            "PLUGIN_INFO = {'id': 'config_options_demo', 'name': 'Config Options Demo', 'api_version': '1.0'}",
            "PARAMETER_SCHEMA = [{'name': 'mode', 'label': '模式', 'type': 'text', 'default': 'default'}]",
            "def describe_config(params, context):",
            "    return {",
            "        'schema_version': 'demo.config.v1',",
            "        'protocol_family': 'plugin_complex_config',",
            "        'config_key': params.get('mode', 'default'),",
            "        'context': {'demo_fields': ['A', 'B']},",
            "        'views': [{'view_id': 'demo.items', 'title': 'Demo Items', 'kind': 'structured_list', 'section': 'items', 'item_schema': {'columns': [{'key': 'field', 'label': '字段', 'type': 'select', 'options_source': {'type': 'plugin_config_context', 'key': 'demo_fields'}}]}}],",
            "    }",
            "def run(input_data, params, context):",
            "    return {'ok': True, 'output': input_data}",
        ]),
        encoding="utf-8",
    )
    return plugin


def write_legacy_only_plugin(root):
    plugin = Path(root) / "legacy_only_plugin.py"
    plugin.write_text(
        "\n".join([
            "PLUGIN_INFO = {'id': 'legacy_only', 'name': 'Legacy Only', 'api_version': '1.0'}",
            "PARAMETER_SCHEMA = []",
            "def open_config_window(parent, current_params, context):",
            "    return dict(current_params)",
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
            described = service.describe_plugin_config(
                "plugin.demo",
                config={"plugin_id": "demo", "params": {"field": "A", "limit": 3}},
                input_table={"headers": ["A"], "rows": [["x"]]},
            )
            default_config = service.make_plugin_default_config("demo")
            node = service.make_default_plugin_node("plugin.demo", node_id="node_demo", include_legacy_type=False)
            custom = service.run_plugin_custom_config_window(
                "demo",
                config={"plugin_id": "demo", "params": {"field": "A", "limit": 3}},
                input_table={"headers": ["A"], "rows": [["x"]]},
            )
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
        self.assertTrue(schema["plugin"]["has_custom_config_window"])
        self.assertTrue(schema["schema"]["capabilities"]["legacy_custom_config"])
        self.assertTrue(schema["schema"]["capabilities"]["schema_config"])
        self.assertFalse(schema["schema"]["capabilities"]["dynamic_options"])
        self.assertFalse(schema["schema"]["capabilities"]["config_description"])
        self.assertFalse(schema["schema"]["capabilities"]["config_patch"])
        self.assertEqual(schema["plugin"]["custom_config_window"]["label"], "兼容旧版设置")
        self.assertTrue(schema["plugin"]["custom_config_window"]["fallback"])
        self.assertTrue(schema["plugin"]["custom_config_window"]["deprecated"])
        self.assertEqual(schema["plugin"]["custom_config_window"]["lifecycle"], "legacy_fallback")
        self.assertFalse(schema["plugin"]["custom_config_window"]["preferred"])
        self.assertEqual(schema["plugin"]["custom_config_window"]["ui_role"], "fallback_action")
        self.assertEqual(schema["plugin"]["custom_config_window"]["ui_prominence"], "low")
        self.assertEqual(schema["plugin"]["custom_config_window"]["ui_placement"], "compatibility_menu")
        self.assertTrue(schema["plugin"]["custom_config_window"]["requires_confirmation"])
        self.assertIn("describe_config", schema["plugin"]["custom_config_window"]["migration_target"])
        self.assertIn("fallback", schema["plugin"]["custom_config_window"]["warning"])
        legacy_state = schema["plugin"]["legacy_config_state"]
        self.assertEqual(legacy_state["schema_version"], "plugin_legacy_config_state.v1")
        self.assertEqual(legacy_state["mode"], "legacy_fallback")
        self.assertEqual(legacy_state["status"], "fallback")
        self.assertTrue(legacy_state["ui_visible"])
        self.assertTrue(legacy_state["fallback"])
        self.assertFalse(legacy_state["required"])
        self.assertFalse(legacy_state["preferred"])
        self.assertEqual(legacy_state["ui_role"], "fallback_action")
        self.assertEqual(legacy_state["ui_prominence"], "low")
        self.assertEqual(legacy_state["ui_placement"], "compatibility_menu")
        self.assertTrue(legacy_state["requires_confirmation"])
        self.assertEqual(legacy_state["primary_config_path"], "schema_form")
        self.assertEqual(schema["schema"]["legacy_config_state"], legacy_state)
        compatibility = schema["plugin"]["config_compatibility"]
        self.assertEqual(compatibility["schema_version"], "plugin_config_compatibility.v1")
        self.assertEqual(compatibility["compatibility_tier"], "B_SCHEMA_FORM")
        self.assertEqual(compatibility["primary_config_path"], "schema_form")
        self.assertEqual(compatibility["ui_recommendation"], "prefer_schema_form")
        self.assertEqual(compatibility["ui_support"]["schema_version"], "plugin_config_ui_support.v1")
        self.assertTrue(compatibility["ui_support"]["standard_supported"])
        self.assertEqual(compatibility["ui_support"]["recommended_entry"], "standard_protocol")
        self.assertTrue(compatibility["ui_support"]["direct_ui"]["dotnet"])
        self.assertTrue(compatibility["ui_support"]["direct_ui"]["web"])
        legacy_policy = compatibility["ui_support"]["legacy_window_policy"]
        self.assertEqual(legacy_policy["schema_version"], "plugin_legacy_window_policy.v1")
        self.assertEqual(legacy_policy["supported_ui"], ["tk", "qt"])
        self.assertIn("dotnet", legacy_policy["unsupported_ui"])
        self.assertFalse(legacy_policy["direct_open_allowed"]["web"])
        self.assertEqual(legacy_state["legacy_window_policy"], legacy_policy)
        self.assertTrue(compatibility["schema_config"])
        self.assertFalse(compatibility["config_patch"])
        self.assertTrue(compatibility["legacy_custom_config"])
        self.assertFalse(compatibility["legacy_ui_required"])
        self.assertTrue(compatibility["legacy_fallback_available"])
        self.assertEqual(compatibility["legacy_lifecycle"], "legacy_fallback")
        self.assertIn("config_patch", compatibility["migration_target"])
        self.assertEqual(schema["schema"]["config_compatibility"], compatibility)
        self.assertTrue(described["ok"])
        self.assertEqual(described["schema_version"], "plugin_config.v1")
        self.assertEqual(described["views"][0]["view_id"], "plugin.params")
        self.assertEqual(described["layout"]["schema_version"], "plugin_config_layout.v1")
        self.assertEqual(described["layout"]["default_view_id"], "plugin.params")
        self.assertIn("plugin.params", described["layout"]["view_order"])
        self.assertEqual(described["layout"]["parameter_groups"][0]["group_key"], "plugin.parameters")
        self.assertEqual(described["ui_hints"]["schema_version"], "plugin_config_ui_hints.v1")
        self.assertEqual(described["ui_hints"]["default_view_id"], "plugin.params")
        self.assertEqual(described["ui_hints"]["view_hints"]["plugin.params"]["kind"], "form")
        self.assertEqual(described["ui_hints"]["parameter_field_hints"]["schema_version"], "plugin_parameter_ui_hints.v1")
        self.assertEqual(described["ui_hints"]["action_prominence"]["open_legacy_config"], "low")
        self.assertEqual(described["protocol_manifest"]["schema_version"], "plugin_config_protocol_manifest.v1")
        self.assertEqual(described["protocol_manifest"]["provider"], "PluginService.describe_plugin_config")
        self.assertTrue(described["protocol_manifest"]["interfaces"]["describe_plugin_config"])
        self.assertTrue(described["protocol_manifest"]["interfaces"]["resolve_plugin_parameter_options"])
        self.assertFalse(described["protocol_manifest"]["interfaces"]["apply_plugin_config_patch"])
        self.assertTrue(described["protocol_manifest"]["interfaces"]["legacy_config_window"])
        self.assertEqual(described["protocol_manifest"]["layout"]["default_view_id"], "plugin.params")
        self.assertEqual(described["protocol_manifest"]["parameter_metadata"]["field_count"], 2)
        self.assertEqual(described["protocol_manifest"]["compatibility"]["legacy_action_ids"], ["open_legacy_config"])
        self.assertEqual(described["protocol_manifest"]["compatibility"]["legacy_window_policy"], legacy_policy)
        self.assertEqual(described["config_compatibility"], compatibility)
        self.assertEqual(described["legacy_config_state"], legacy_state)
        self.assertEqual(described["actions"][0]["action_id"], "open_legacy_config")
        self.assertTrue(described["actions"][0]["fallback"])
        self.assertTrue(described["actions"][0]["deprecated"])
        self.assertEqual(described["actions"][0]["mode"], "legacy_fallback")
        self.assertEqual(described["actions"][0]["legacy_config_state"]["schema_version"], "plugin_legacy_config_state.v1")
        self.assertEqual(described["actions"][0]["legacy_window_policy"], legacy_policy)
        self.assertEqual(described["actions"][0]["lifecycle"], "legacy_fallback")
        self.assertFalse(described["actions"][0]["preferred"])
        self.assertEqual(described["actions"][0]["ui_role"], "fallback_action")
        self.assertEqual(described["actions"][0]["ui_prominence"], "low")
        self.assertEqual(described["actions"][0]["ui_placement"], "compatibility_menu")
        self.assertTrue(described["actions"][0]["requires_confirmation"])
        self.assertIn("config_patch", described["actions"][0]["migration_target"])
        self.assertIn("schema/patch", described["actions"][0]["warning"])
        self.assertEqual(described["input_data"]["tables"], ["primary", "workflow_current", "当前表"])
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
        self.assertTrue(custom["ok"])
        self.assertTrue(custom["changed"])
        self.assertEqual(custom["config"]["params"]["limit"], 9)
        self.assertGreaterEqual(custom["params"]["table_count"], 1)
        self.assertTrue(custom["params"]["has_plugin_data_dir"])
        self.assertTrue(run["ok"])
        self.assertEqual(run["result"]["headers"], ["A"])
        self.assertEqual(run["result"]["rows"], [["x"]])

    def test_plugin_parameter_schema_maps_extended_ui_types(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            plugin = Path(temp_dir) / "extended_plugin.py"
            plugin.write_text(
                "\n".join([
                    "PLUGIN_INFO = {'id': 'extended', 'name': 'Extended', 'api_version': '1.0'}",
                    "SETTINGS_FILE = 'extended_settings.json'",
                    "PARAMETER_SCHEMA = [",
                    "    {'name': 'table_name', 'label': '数据表', 'type': 'table_select', 'default': 'orders', 'group': '输入', 'group_order': 10, 'order': 1, 'empty_text': '没有表'},",
                    "    {'name': 'input_alias', 'label': '输入表', 'type': 'input_table_select', 'default': '当前表'},",
                    "    {'name': 'config_name', 'label': '配置', 'type': 'dynamic_select', 'default': 'default', 'allow_custom': True},",
                    "    {'name': 'directory_path', 'label': '目录', 'type': 'folder_path', 'default': '', 'advanced': True, 'placeholder': '选择插件目录', 'warning': '目录不存在时运行会失败', 'invalid_value_text': '请选择有效目录', 'visible_when': {'field': 'input_alias', 'equals': '当前表'}, 'enabled_when': {'field': 'config_name', 'truthy': True}},",
                    "]",
                    "def get_dynamic_parameter_options(param_name, params, context):",
                    "    return ['default', 'advanced'] if param_name == 'config_name' else []",
                    "def run(input_data, params, context):",
                    "    return {'ok': True, 'output': input_data}",
                ]),
                encoding="utf-8",
            )
            service = PluginService(plugins_dir=temp_dir, app_dir=temp_dir)
            schema = service.get_plugin_schema("plugin.extended")
            described = service.describe_plugin_config(
                "plugin.extended",
                config={"plugin_id": "extended", "params": {"config_name": "default"}},
            )
            dynamic_options = service.resolve_plugin_parameter_options(
                "plugin.extended",
                param_key="config_name",
                config={"plugin_id": "extended", "params": {"config_name": "default"}},
            )
            table_options = service.resolve_plugin_parameter_options(
                "plugin.extended",
                field_key="params.table_name",
                config={"plugin_id": "extended", "params": {"config_name": "default"}},
                context={"table_names": ["orders", "archive"]},
            )
            visible_state = service.resolve_plugin_parameter_field_state(
                "plugin.extended",
                config={"plugin_id": "extended", "params": {"input_alias": "当前表", "config_name": "default"}},
                changed_fields=["params.config_name"],
            )
            hidden_state = service.resolve_plugin_parameter_field_state(
                "plugin.extended",
                field_key="params.directory_path",
                config={"plugin_id": "extended", "params": {"input_alias": "其他表", "config_name": ""}},
            )

        self.assertTrue(schema["ok"])
        self.assertEqual(schema["schema"]["parameters"][0]["name"], "table_name")
        group_titles = [group["title"] for group in schema["schema"]["form"]["groups"]]
        self.assertIn("插件参数", group_titles)
        self.assertIn("插件参数 / 输入", group_titles)
        self.assertIn("高级参数", group_titles)
        fields = {
            field["key"]: field
            for group in schema["schema"]["form"]["groups"]
            for field in group["fields"]
        }
        input_group = next(group for group in schema["schema"]["form"]["groups"] if group["title"] == "插件参数 / 输入")
        self.assertEqual([field["key"] for field in input_group["fields"]], ["params.table_name"])
        advanced_group = next(group for group in schema["schema"]["form"]["groups"] if group["title"] == "高级参数")
        self.assertTrue(advanced_group["advanced"])
        self.assertEqual([field["key"] for field in advanced_group["fields"]], ["params.directory_path"])
        self.assertEqual(fields["params.table_name"]["type"], "table_select")
        self.assertEqual(fields["params.table_name"]["options_source"], {"type": "table_names"})
        self.assertEqual(fields["params.table_name"]["action"]["key"], "pick_table_name")
        self.assertEqual(fields["params.table_name"]["group"], "输入")
        self.assertEqual(fields["params.table_name"]["empty_text"], "没有表")
        self.assertEqual(fields["params.input_alias"]["type"], "select")
        self.assertEqual(fields["params.input_alias"]["options_source"], {"type": "plugin_input_tables"})
        self.assertEqual(fields["params.input_alias"]["action"]["key"], "pick_plugin_input_table")
        self.assertEqual(fields["params.config_name"]["type"], "select")
        self.assertEqual(fields["params.config_name"]["options_source"]["type"], "plugin_dynamic_choices")
        self.assertEqual(fields["params.config_name"]["options_source"]["param_key"], "config_name")
        self.assertTrue(schema["schema"]["capabilities"]["dynamic_options"])
        self.assertTrue(schema["schema"]["capabilities"]["schema_config"])
        self.assertEqual(fields["params.directory_path"]["type"], "directory")
        self.assertEqual(fields["params.directory_path"]["action"]["key"], "browse_directory")
        self.assertTrue(fields["params.directory_path"]["advanced"])
        self.assertEqual(fields["params.directory_path"]["placeholder"], "选择插件目录")
        self.assertEqual(fields["params.directory_path"]["warning"], "目录不存在时运行会失败")
        self.assertEqual(fields["params.directory_path"]["invalid_value_text"], "请选择有效目录")
        self.assertEqual(fields["params.directory_path"]["visible_when"], {"field": "params.input_alias", "equals": "当前表"})
        self.assertEqual(fields["params.directory_path"]["enabled_when"], {"field": "params.config_name", "truthy": True})
        metadata = schema["schema"]["parameter_metadata"]
        self.assertEqual(metadata["schema_version"], "plugin_parameters.v1")
        self.assertEqual(metadata["plugin_id"], "extended")
        self.assertEqual(metadata["field_count"], 4)
        self.assertEqual(metadata["default_params"]["table_name"], "orders")
        self.assertEqual(set(metadata["context_requirements"]["options_sources"]), {"table_names", "plugin_input_tables", "plugin_dynamic_choices"})
        self.assertTrue(metadata["context_requirements"]["needs_table_names"])
        self.assertTrue(metadata["context_requirements"]["needs_plugin_input_tables"])
        self.assertTrue(metadata["context_requirements"]["needs_dynamic_options"])
        self.assertTrue(metadata["capabilities"]["dynamic_options"])
        self.assertTrue(metadata["capabilities"]["conditional_fields"])
        self.assertTrue(metadata["capabilities"]["field_actions"])
        self.assertTrue(metadata["capabilities"]["advanced_fields"])
        self.assertEqual(metadata["layout_index"]["schema_version"], "plugin_parameter_layout.v1")
        self.assertEqual(metadata["ui_hints"]["schema_version"], "plugin_parameter_ui_hints.v1")
        self.assertEqual(metadata["field_state_schema"]["schema_version"], "plugin_parameter_field_state.v1")
        self.assertEqual(metadata["field_state_index"]["params.directory_path"]["visible_when"], {"field": "params.input_alias", "equals": "当前表"})
        self.assertEqual(metadata["field_state_index"]["params.directory_path"]["enabled_when"], {"field": "params.config_name", "truthy": True})
        self.assertTrue(metadata["field_state_index"]["params.directory_path"]["has_warning"])
        self.assertEqual(metadata["field_state_index"]["params.config_name"]["options_source"]["type"], "plugin_dynamic_choices")
        self.assertTrue(metadata["field_state_index"]["params.config_name"]["needs_options_refresh"])
        self.assertIn("params.directory_path", metadata["layout_index"]["field_order"])
        self.assertIn("params.directory_path", metadata["ui_hints"]["advanced_fields"])
        self.assertIn("params.directory_path", metadata["ui_hints"]["placeholder_fields"])
        self.assertIn("params.directory_path", metadata["ui_hints"]["warning_fields"])
        metadata_groups = {group["title"]: group for group in metadata["groups"]}
        self.assertEqual(metadata_groups["插件参数 / 输入"]["field_keys"], ["params.table_name"])
        self.assertEqual(metadata_groups["高级参数"]["param_keys"], ["directory_path"])
        self.assertEqual(metadata["field_index"]["params.table_name"]["config_path"], ["params", "table_name"])
        self.assertEqual(metadata["field_index"]["params.table_name"]["group"], "插件参数 / 输入")
        self.assertEqual(metadata["field_index"]["params.config_name"]["options_source"]["type"], "plugin_dynamic_choices")
        self.assertEqual(metadata["group_index"]["plugin.parameters.插件参数_输入"]["param_keys"], ["table_name"])
        self.assertEqual(metadata["dependency_index"]["params.input_alias"], ["params.directory_path"])
        self.assertEqual(metadata["dependency_index"]["params.config_name"], ["params.directory_path"])
        self.assertEqual(
            [item["field_key"] for item in metadata["options_source_index"]["table_names"]],
            ["params.table_name"],
        )
        self.assertEqual(
            [item["field_key"] for item in metadata["options_source_index"]["plugin_input_tables"]],
            ["params.input_alias"],
        )
        self.assertEqual(
            metadata["options_source_index"]["plugin_dynamic_choices"][0]["options_source"]["param_key"],
            "config_name",
        )
        self.assertEqual(metadata["options_source_details"]["table_names"]["label"], "SQLite 数据库表")
        self.assertEqual(metadata["options_source_details"]["table_names"]["field_count"], 1)
        self.assertEqual(
            metadata["options_source_details"]["plugin_dynamic_choices"]["field_keys"],
            ["params.config_name"],
        )
        self.assertTrue(metadata["options_source_details"]["plugin_dynamic_choices"]["dynamic"])
        metadata_fields = {field["key"]: field for field in metadata["fields"]}
        self.assertEqual(metadata_fields["params.input_alias"]["options_source"], {"type": "plugin_input_tables"})
        self.assertEqual(metadata_fields["params.directory_path"]["visible_when"], {"field": "params.input_alias", "equals": "当前表"})
        described_fields = {
            field["key"]: field
            for group in described["node_ui_schema"]["form"]["groups"]
            for field in group["fields"]
        }
        self.assertEqual(described_fields["params.config_name"]["choices"], ["default", "advanced"])
        described_metadata_fields = {
            field["key"]: field
            for field in described["parameter_metadata"]["fields"]
        }
        self.assertEqual(described_metadata_fields["params.config_name"]["choices"], ["default", "advanced"])
        self.assertEqual(
            described["node_ui_schema"]["parameter_metadata"]["fields"],
            described["parameter_metadata"]["fields"],
        )
        self.assertEqual(
            described["node_ui_schema"]["parameter_metadata"]["field_index"],
            described["parameter_metadata"]["field_index"],
        )
        self.assertEqual(
            described["node_ui_schema"]["parameter_metadata"]["layout_index"],
            described["parameter_metadata"]["layout_index"],
        )
        self.assertEqual(
            described["node_ui_schema"]["parameter_metadata"]["ui_hints"],
            described["parameter_metadata"]["ui_hints"],
        )
        self.assertEqual(described["protocol_manifest"]["schema_version"], "plugin_config_protocol_manifest.v1")
        self.assertTrue(described["protocol_manifest"]["interfaces"]["resolve_plugin_parameter_options"])
        self.assertTrue(described["protocol_manifest"]["interfaces"]["resolve_plugin_parameter_field_state"])
        self.assertFalse(described["protocol_manifest"]["interfaces"]["legacy_config_window"])
        self.assertEqual(described["protocol_manifest"]["schemas"]["parameter_field_state"], "plugin_parameter_field_state.v1")
        self.assertEqual(described["protocol_manifest"]["parameter_metadata"]["field_state_schema"], "plugin_parameter_field_state.v1")
        self.assertEqual(described["protocol_manifest"]["parameter_metadata"]["field_state_count"], 4)
        self.assertEqual(
            set(described["protocol_manifest"]["parameter_metadata"]["options_sources"]),
            {"table_names", "plugin_input_tables", "plugin_dynamic_choices"},
        )
        self.assertTrue(described["protocol_manifest"]["parameter_metadata"]["capabilities"]["conditional_fields"])
        self.assertIn("plugin.resources", described["protocol_manifest"]["layout"]["secondary_views"])
        self.assertEqual(dynamic_options["schema_version"], "plugin_parameter_options.v1")
        self.assertEqual(dynamic_options["param_key"], "config_name")
        self.assertEqual(dynamic_options["choices"], ["default", "advanced"])
        self.assertTrue(dynamic_options["dynamic"])
        self.assertEqual(table_options["field_key"], "params.table_name")
        self.assertEqual(table_options["choices"], ["orders", "archive"])
        self.assertFalse(table_options["dynamic"])
        self.assertEqual(visible_state["schema_version"], "plugin_parameter_field_runtime_state.v1")
        self.assertEqual(visible_state["plugin_id"], "extended")
        self.assertEqual(visible_state["field_count"], 4)
        directory_runtime = visible_state["field_state_index"]["params.directory_path"]
        self.assertTrue(directory_runtime["visible"])
        self.assertTrue(directory_runtime["enabled"])
        self.assertEqual(directory_runtime["status"], "active")
        self.assertEqual(directory_runtime["current_value"], "")
        self.assertTrue(directory_runtime["refresh_triggered"])
        self.assertTrue(directory_runtime["needs_options_refresh"])
        self.assertIn("params.config_name", directory_runtime["condition_dependencies"])
        self.assertEqual(directory_runtime["warning"], "目录不存在时运行会失败")
        self.assertEqual(visible_state["field_state_index"]["params.config_name"]["dependents"], ["params.directory_path"])
        self.assertTrue(hidden_state["ok"])
        self.assertEqual(hidden_state["field_count"], 1)
        self.assertFalse(hidden_state["fields"][0]["visible"])
        self.assertFalse(hidden_state["fields"][0]["enabled"])
        self.assertEqual(hidden_state["fields"][0]["status"], "hidden")
        self.assertEqual(described["resources"][0]["file"], "extended_settings.json")
        self.assertEqual(described["views"][1]["kind"], "resource_list")

    def test_legacy_only_plugin_marks_non_standard_ui_unsupported(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            write_legacy_only_plugin(temp_dir)
            service = PluginService(plugins_dir=temp_dir, app_dir=temp_dir)
            schema = service.get_plugin_schema("plugin.legacy_only")
            described = service.describe_plugin_config("plugin.legacy_only")

        compatibility = schema["plugin"]["config_compatibility"]
        self.assertEqual(compatibility["compatibility_tier"], "C_LEGACY_REQUIRED")
        self.assertEqual(compatibility["primary_config_path"], "legacy_custom_config")
        self.assertTrue(compatibility["legacy_ui_required"])
        self.assertFalse(compatibility["ui_support"]["standard_supported"])
        self.assertEqual(compatibility["ui_support"]["recommended_entry"], "legacy_window")
        self.assertTrue(compatibility["ui_support"]["legacy_window_policy"]["required"])
        self.assertEqual(compatibility["ui_support"]["legacy_window_policy"]["supported_ui"], ["tk", "qt"])
        self.assertIn("web", compatibility["ui_support"]["legacy_window_policy"]["unsupported_ui"])
        self.assertTrue(compatibility["ui_support"]["direct_ui"]["qt"])
        self.assertFalse(compatibility["ui_support"]["direct_ui"]["dotnet"])
        self.assertFalse(compatibility["ui_support"]["direct_ui"]["web"])
        self.assertEqual(described["legacy_config_state"]["mode"], "legacy_required")
        sections = {section["section_id"]: section for section in described["config_sections"]}
        compatibility_text = "\n".join(sections["plugin.config_compatibility"]["lines"])
        self.assertIn("兼容等级 C_LEGACY_REQUIRED", compatibility_text)
        self.assertIn("可直接支持UI：Tk、Qt", compatibility_text)

    def test_plugin_config_description_merges_plugin_extension(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            plugin = Path(temp_dir) / "protocol_plugin.py"
            plugin.write_text(
                "\n".join([
                    "PLUGIN_INFO = {'id': 'protocol_demo', 'name': 'Protocol Demo', 'api_version': '1.0'}",
                    "PARAMETER_SCHEMA = []",
                    "def describe_config(params, context):",
                    "    return {",
                    "        'schema_version': 'demo.config.v1',",
                    "        'protocol_family': 'plugin_complex_config',",
                    "        'config_key': 'demo',",
                    "        'summary': {'items': 1},",
                    "        'context': {'choices': {'modes': ['A', 'B']}},",
                    "        'models': {'item_default': {'name': ''}},",
                    "        'capabilities': {'config_patch': True},",
                    "        'views': [{'view_id': 'demo.items', 'title': 'Demo Items', 'kind': 'structured_list'}],",
                    "        'resources': [{'resource_id': 'demo.resource', 'label': 'Demo Resource', 'kind': 'json_file'}],",
                    "        'actions': [{'action_id': 'demo.edit', 'label': 'Edit Demo', 'kind': 'config_editor'}],",
            "        'warnings': [",
            "            'demo warning',",
            "            {'code': 'demo_structured_warning', 'level': 'warning', 'message': 'structured warning', 'view_id': 'demo.items'},",
            "            {'code': 'demo_target_warning', 'level': 'warning', 'message': 'target warning', 'target': {'view_id': 'demo.items', 'field': 'name'}},",
            "        ],",
            "    }",
            "def preview_config_effect(params, context):",
            "    return {",
            "        'schema_version': 'demo.effect.v1',",
            "        'summary': {'items': 2},",
            "        'required_input_tables': [{'alias': '当前表', 'required': True}],",
            "        'expected_output_fields': ['A', 'B'],",
            "        'side_effects': [{'kind': 'read_input_tables', 'label': '读取输入表'}],",
            "    }",
            "def run(input_data, params, context):",
            "    return {'ok': True, 'output': input_data}",
        ]),
        encoding="utf-8",
            )
            service = PluginService(plugins_dir=temp_dir, app_dir=temp_dir)
            described = service.describe_plugin_config("plugin.protocol_demo")
            effect = service.preview_plugin_config_effect("plugin.protocol_demo")

        self.assertTrue(described["ok"])
        self.assertEqual(described["config_schema_version"], "demo.config.v1")
        self.assertEqual(described["protocol_family"], "plugin_complex_config")
        self.assertEqual(described["config_key"], "demo")
        self.assertEqual(described["summary"]["items"], 1)
        self.assertEqual(described["context"]["choices"]["modes"], ["A", "B"])
        self.assertEqual(described["models"]["item_default"], {"name": ""})
        self.assertTrue(described["capabilities"]["config_patch"])
        self.assertTrue(described["capabilities"]["config_effect_preview"])
        self.assertEqual(described["config_effect"]["schema_version"], "demo.effect.v1")
        view_by_id = {view["view_id"]: view for view in described["views"]}
        self.assertIn("plugin.config_effect", view_by_id)
        effect_state = described["config_effect"]["effect_state"]
        self.assertEqual(effect_state["schema_version"], "plugin_config_effect_state.v1")
        self.assertEqual(effect_state["status"], "ok")
        self.assertEqual(effect_state["expected_output_fields"], ["A", "B"])
        self.assertEqual(effect_state["required_input_tables"][0]["alias"], "当前表")
        self.assertEqual(effect_state["side_effects"][0]["kind"], "read_input_tables")
        self.assertEqual(view_by_id["plugin.config_effect"]["state"]["schema_version"], "plugin_config_effect_state.v1")
        self.assertTrue(effect["ok"])
        self.assertEqual(effect["expected_output_fields"], ["A", "B"])
        self.assertEqual(effect["effect_state"]["status_message"], "配置效果预览：输入表 1 个，输出字段 2 个，运行影响 1 项。")
        self.assertEqual(described["plugin_extension"]["schema_version"], "demo.config.v1")
        self.assertIn("demo.items", [view["view_id"] for view in described["views"]])
        self.assertIn("demo.resource", [resource["resource_id"] for resource in described["resources"]])
        self.assertIn("demo.edit", [action["action_id"] for action in described["actions"]])
        config_sections = {section["section_id"]: section for section in described["config_sections"]}
        self.assertIn("plugin.config_protocol", config_sections)
        self.assertIn("plugin.parameter_metadata", config_sections)
        protocol_lines = "\n".join(config_sections["plugin.config_protocol"]["lines"])
        self.assertIn("配置视图：插件参数、Demo Items、配置效果、插件资源", protocol_lines)
        self.assertIn("配置资源：Demo Resource", protocol_lines)
        self.assertIn("配置动作：Edit Demo", protocol_lines)
        metadata_lines = "\n".join(config_sections["plugin.parameter_metadata"]["lines"])
        self.assertIn("参数字段：0 个", metadata_lines)
        self.assertIn("demo warning", described["warnings"])
        self.assertIn("structured warning", described["warnings"])
        warning_by_code = {item["code"]: item for item in described["warning_items"]}
        self.assertEqual(warning_by_code["plugin_config_warning_1"]["message"], "demo warning")
        self.assertEqual(warning_by_code["plugin_config_warning_1"]["source"], "plugin_config")
        self.assertEqual(warning_by_code["plugin_config_warning_1"]["plugin_id"], "protocol_demo")
        self.assertEqual(
            warning_by_code["plugin_config_warning_1"]["target"]["schema_version"],
            "plugin_config_warning_target.v1",
        )
        self.assertFalse(warning_by_code["plugin_config_warning_1"]["target"]["can_focus_view"])
        self.assertEqual(warning_by_code["demo_structured_warning"]["view_id"], "demo.items")
        self.assertEqual(warning_by_code["demo_structured_warning"]["target"]["view_id"], "demo.items")
        self.assertEqual(warning_by_code["demo_structured_warning"]["target"]["focus_path"], "/views/demo.items")
        self.assertTrue(warning_by_code["demo_structured_warning"]["target"]["can_focus_view"])
        self.assertEqual(warning_by_code["demo_target_warning"]["target"]["schema_version"], "plugin_config_warning_target.v1")
        self.assertEqual(warning_by_code["demo_target_warning"]["target"]["view_id"], "demo.items")
        self.assertEqual(warning_by_code["demo_target_warning"]["target"]["field"], "name")
        self.assertEqual(warning_by_code["demo_target_warning"]["target"]["focus_path"], "/views/demo.items/fields/name")
        self.assertTrue(warning_by_code["demo_target_warning"]["target"]["can_focus_field"])

    def test_plugin_config_patch_validates_applies_and_refreshes_description(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            write_patch_plugin(temp_dir)
            service = PluginService(plugins_dir=temp_dir, app_dir=temp_dir)
            config = {"plugin_id": "patch_demo", "params": {"mode": "old"}}
            patch = {"operation": "set_param", "key": "mode", "value": "new"}
            validation = service.validate_plugin_config_patch("plugin.patch_demo", config=config, patch=patch)
            applied = service.apply_plugin_config_patch("plugin.patch_demo", config=config, patch=patch)
            invalid = service.validate_plugin_config_patch(
                "plugin.patch_demo",
                config=config,
                patch={"operation": "delete_everything"},
            )

        self.assertTrue(validation["ok"])
        self.assertEqual(validation["patch"], patch)
        self.assertTrue(applied["ok"])
        self.assertTrue(applied["changed"])
        self.assertEqual(applied["config"]["params"]["mode"], "new")
        self.assertEqual(applied["patch_result"]["schema_version"], "plugin_config_patch_result.v1")
        self.assertEqual(applied["patch_result"]["plugin_id"], "patch_demo")
        self.assertTrue(applied["patch_result"]["changed"])
        self.assertEqual(applied["patch_result"]["patch_summary"]["operation"], "set_param")
        self.assertEqual(applied["patch_result"]["target"]["schema_version"], "plugin_config_patch_target.v1")
        self.assertEqual(applied["patch_result"]["target"]["operation"], "set_param")
        self.assertFalse(applied["patch_result"]["target"]["can_focus_view"])
        self.assertEqual(applied["patch_result"]["description_summary"]["schema_version"], "patch_demo.config.v1")
        self.assertEqual(applied["patch_result"]["description_summary"]["summary"], {"mode": "new"})
        self.assertEqual(applied["patch_result"]["config_effect_summary"]["预期输出字段"], ["A"])
        self.assertEqual(applied["description"]["config_schema_version"], "patch_demo.config.v1")
        self.assertEqual(applied["description"]["protocol_family"], "plugin_form_config")
        self.assertEqual(applied["description"]["summary"]["mode"], "new")
        self.assertEqual(applied["description"]["plugin_extension"]["summary"]["mode"], "new")
        self.assertEqual(applied["description"]["config_compatibility"]["primary_config_path"], "schema_patch")
        self.assertEqual(applied["description"]["config_compatibility"]["compatibility_tier"], "A_SCHEMA_PATCH")
        self.assertTrue(applied["description"]["config_compatibility"]["ui_support"]["direct_ui"]["dotnet"])
        self.assertTrue(applied["description"]["config_compatibility"]["ui_support"]["direct_ui"]["web"])
        self.assertTrue(applied["description"]["config_compatibility"]["config_patch"])
        self.assertFalse(applied["description"]["config_compatibility"]["legacy_custom_config"])
        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["issues"][0]["code"], "plugin_config_patch_invalid")

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
            described = worker.handle_request(request("describe_plugin_config", {
                "plugin_id": "plugin.demo",
                "plugins_dir": temp_dir,
                "input_table": {"headers": ["A"], "rows": [["x"]]},
            }))
            resolved_options = worker.handle_request(request("resolve_plugin_parameter_options", {
                "plugin_id": "plugin.demo",
                "plugins_dir": temp_dir,
                "field_key": "params.field",
                "input_table": {"headers": ["A", "B"], "rows": [["x", "y"]]},
            }))
            field_state = worker.handle_request(request("resolve_plugin_parameter_field_state", {
                "plugin_id": "plugin.demo",
                "plugins_dir": temp_dir,
                "field_key": "params.field",
                "config": {"plugin_id": "demo", "params": {"field": "A", "limit": 3}},
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
        self.assertEqual(
            schema["result"]["schema"]["legacy_config_state"]["schema_version"],
            "plugin_legacy_config_state.v1",
        )
        self.assertEqual(schema["result"]["schema"]["legacy_config_state"]["mode"], "legacy_fallback")
        self.assertEqual(
            schema["result"]["schema"]["parameter_metadata"]["layout_index"]["schema_version"],
            "plugin_parameter_layout.v1",
        )
        self.assertEqual(
            schema["result"]["schema"]["parameter_metadata"]["ui_hints"]["schema_version"],
            "plugin_parameter_ui_hints.v1",
        )
        self.assertEqual(
            schema["result"]["schema"]["parameter_metadata"]["options_source_index"]["preview_headers"][0]["field_key"],
            "params.field",
        )
        self.assertTrue(described["ok"])
        self.assertEqual(described["result"]["schema_version"], "plugin_config.v1")
        self.assertEqual(
            described["result"]["legacy_config_state"]["schema_version"],
            "plugin_legacy_config_state.v1",
        )
        self.assertEqual(described["result"]["views"][0]["kind"], "form")
        self.assertEqual(
            described["result"]["parameter_metadata"]["layout_index"]["schema_version"],
            "plugin_parameter_layout.v1",
        )
        self.assertEqual(
            described["result"]["parameter_metadata"]["ui_hints"]["schema_version"],
            "plugin_parameter_ui_hints.v1",
        )
        self.assertEqual(described["result"]["layout"]["schema_version"], "plugin_config_layout.v1")
        self.assertEqual(described["result"]["layout"]["default_view_id"], "plugin.params")
        self.assertIn("plugin.params", described["result"]["layout"]["view_order"])
        self.assertEqual(described["result"]["ui_hints"]["schema_version"], "plugin_config_ui_hints.v1")
        self.assertEqual(described["result"]["ui_hints"]["view_hints"]["plugin.params"]["kind"], "form")
        view_by_id = {view["view_id"]: view for view in described["result"]["views"]}
        self.assertIn("plugin.parameter_metadata", view_by_id)
        self.assertEqual(view_by_id["plugin.parameter_metadata"]["kind"], "summary")
        self.assertEqual(view_by_id["plugin.parameter_metadata"]["summary"]["field_count"], 2)
        self.assertEqual(described["result"]["actions"][0]["legacy_config_state"]["mode"], "legacy_fallback")
        self.assertTrue(resolved_options["ok"])
        self.assertEqual(resolved_options["result"]["schema_version"], "plugin_parameter_options.v1")
        self.assertEqual(resolved_options["result"]["choices"], ["A", "B"])
        self.assertEqual(resolved_options["result"]["options_source"], {"type": "preview_headers"})
        self.assertTrue(field_state["ok"])
        self.assertEqual(field_state["result"]["schema_version"], "plugin_parameter_field_runtime_state.v1")
        self.assertEqual(field_state["result"]["fields"][0]["field_key"], "params.field")
        self.assertTrue(field_state["result"]["fields"][0]["visible"])
        self.assertTrue(field_state["result"]["fields"][0]["enabled"])
        self.assertTrue(default_config["ok"])
        self.assertEqual(default_config["result"]["config"]["params"]["field"], "A")
        self.assertTrue(run["ok"])
        self.assertEqual(run["result"]["result"]["headers"], ["A"])

    def test_stdio_worker_resolves_plugin_config_options(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            write_config_options_plugin(temp_dir)
            worker = StdioWorker()

            response = worker.handle_request(request("resolve_plugin_config_options", {
                "plugin_id": "plugin.config_options_demo",
                "plugins_dir": temp_dir,
                "field_key": "field",
                "view_id": "demo.items",
                "section": "items",
                "config": {"plugin_id": "config_options_demo", "params": {"mode": "default"}},
            }))

        self.assertTrue(response["ok"])
        result = response["result"]
        self.assertEqual(result["schema_version"], "DataFlowKit.plugin_config_options.v1")
        self.assertEqual(result["plugin_id"], "config_options_demo")
        self.assertEqual(result["protocol_family"], "plugin_complex_config")
        self.assertEqual(result["source"], "demo_fields")
        self.assertEqual(result["choices"], ["A", "B"])
        self.assertEqual(result["view_id"], "demo.items")
        self.assertEqual(result["section"], "items")

    def test_stdio_worker_exposes_plugin_config_patch_actions(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            write_patch_plugin(temp_dir)
            worker = StdioWorker()
            config = {"plugin_id": "patch_demo", "params": {"mode": "old"}}
            patch = {"operation": "set_param", "key": "mode", "value": "stdio"}

            validation = worker.handle_request(request("validate_plugin_config_patch", {
                "plugin_id": "plugin.patch_demo",
                "plugins_dir": temp_dir,
                "config": config,
                "patch": patch,
            }))
            applied = worker.handle_request(request("apply_plugin_config_patch", {
                "plugin_id": "plugin.patch_demo",
                "plugins_dir": temp_dir,
                "config": config,
                "patch": patch,
            }))
            effect = worker.handle_request(request("preview_plugin_config_effect", {
                "plugin_id": "plugin.patch_demo",
                "plugins_dir": temp_dir,
                "config": config,
            }))

        self.assertTrue(validation["ok"])
        self.assertTrue(validation["result"]["ok"])
        self.assertTrue(applied["ok"])
        self.assertEqual(applied["result"]["config"]["params"]["mode"], "stdio")
        self.assertEqual(applied["result"]["patch_result"]["schema_version"], "plugin_config_patch_result.v1")
        self.assertEqual(applied["result"]["patch_result"]["description_summary"]["summary"], {"mode": "stdio"})
        self.assertEqual(applied["result"]["description"]["plugin_extension"]["summary"]["mode"], "stdio")
        self.assertTrue(effect["ok"])
        self.assertEqual(effect["result"]["schema_version"], "patch_demo.effect.v1")
        self.assertEqual(effect["result"]["effect_state"]["schema_version"], "plugin_config_effect_state.v1")
        self.assertEqual(effect["result"]["summary"]["mode"], "old")

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
