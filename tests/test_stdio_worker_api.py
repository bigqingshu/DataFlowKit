# -*- coding: utf-8 -*-
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.stdio_worker import StdioWorker, iter_json_lines


def request(action, payload=None, request_id="req1"):
    return {
        "request_id": request_id,
        "api_version": "1.0",
        "action": action,
        "payload": payload or {},
    }


class StdioWorkerApiTests(unittest.TestCase):
    def test_list_node_types_and_get_node_type(self):
        worker = StdioWorker()

        listed = worker.handle_request(request("list_node_types", {"include_unsupported": False}))
        node_type = worker.handle_request(request("get_node_type", {"node_type_id": "core.new_columns", "preview_headers": ["A"]}))

        self.assertTrue(listed["ok"])
        self.assertIn("新建列", listed["result"]["node_types"])
        self.assertIn("core.new_columns", listed["result"]["node_type_ids"])
        self.assertIn("core.file_list", listed["result"]["node_type_ids"])
        self.assertTrue(all(item["supported_headless"] for item in listed["result"]["node_catalog"]))
        self.assertNotIn("插件节点", listed["result"]["node_types"])
        self.assertNotIn("core.plugin", listed["result"]["node_type_ids"])
        self.assertTrue(node_type["ok"])
        self.assertEqual(node_type["result"]["node_type_id"], "core.new_columns")
        self.assertEqual(node_type["result"]["node_type"], "新建列")
        self.assertEqual(node_type["result"]["display_name"], "新建列")
        self.assertTrue(node_type["result"]["supported"])
        self.assertIn("columns_text", node_type["result"]["default_config"])

    def test_node_ui_schema_actions_return_renderable_metadata(self):
        worker = StdioWorker()

        listed = worker.handle_request(request("list_node_ui_schemas", {
            "include_unsupported": False,
            "preview_headers": ["A", "B"],
        }))
        schema = worker.handle_request(request("get_node_ui_schema", {
            "node_type_id": "core.replace",
            "preview_headers": ["A", "B"],
        }))

        self.assertTrue(listed["ok"])
        self.assertIn("node_ui_schemas", listed["result"])
        self.assertIn("core.new_columns", [item["node_type_id"] for item in listed["result"]["node_ui_schemas"]])
        self.assertTrue(schema["ok"])
        self.assertEqual(schema["result"]["node_type_id"], "core.replace")
        self.assertEqual(schema["result"]["schema_version"], "2.0")
        self.assertEqual(schema["result"]["form"]["schema_version"], "2.0")
        self.assertEqual(schema["result"]["category_label"], "数据处理")
        self.assertIn("批量替换", schema["result"]["menu"]["path"])
        self.assertEqual(schema["result"]["menu"]["group"], "数据处理")
        self.assertEqual(schema["result"]["menu"]["submenu"], ["批量替换"])
        target_fields = [
            field
            for group in schema["result"]["form"]["groups"]
            for field in group["fields"]
            if field["key"] == "target_field"
        ]
        self.assertEqual(target_fields[0]["type"], "field_select")
        self.assertEqual(target_fields[0]["choices"], ["A", "B"])

    def test_node_ui_schema_includes_shared_warning_and_context_metadata(self):
        worker = StdioWorker()

        loop_schema = worker.handle_request(request("get_node_ui_schema", {
            "node_type_id": "core.loop_judge",
            "preview_headers": ["A"],
        }))
        self.assertTrue(loop_schema["ok"])
        self.assertTrue(loop_schema["result"]["warning_items"])
        self.assertEqual(loop_schema["result"]["warning_items"][0]["level"], "warning")

        loop_fields = [
            field
            for group in loop_schema["result"]["form"]["groups"]
            for field in group["fields"]
            if field["key"] == "loop_id"
        ]
        self.assertEqual(loop_fields[0]["context_requirements"][0]["kind"], "plan_refs")
        self.assertEqual(loop_fields[0]["context_requirements"][0]["ref_kind"], "loop_id")

        write_schema = worker.handle_request(request("get_node_ui_schema", {
            "node_type_id": "字段映射写入表",
            "preview_headers": ["源字段"],
            "table_names": ["orders", "result"],
            "table_columns": {"orders": ["id", "name"], "result": ["row_id", "status"]},
        }))
        self.assertTrue(write_schema["ok"])
        write_fields = {
            field["key"]: field
            for group in write_schema["result"]["form"]["groups"]
            for field in group["fields"]
        }
        mapping_columns = {
            item["key"]: item
            for item in write_fields["field_mappings"]["item_schema"]["columns"]
        }
        self.assertEqual(mapping_columns["source_field"]["context_requirements"][0]["kind"], "table_columns")
        self.assertEqual(mapping_columns["source_field"]["context_requirements"][1]["field"], "source_table")

    def test_plugin_schema_and_description_expose_parameter_layout_over_stdio(self):
        worker = StdioWorker()

        with TemporaryDirectory() as temp_dir:
            plugin_path = Path(temp_dir) / "stdio_demo_plugin.py"
            plugin_path.write_text(
                "\n".join([
                    "PLUGIN_INFO = {'id': 'stdio_demo', 'name': 'Stdio Demo', 'api_version': '1.0'}",
                    "PARAMETER_SCHEMA = [",
                    "    {'name': 'field', 'label': '字段', 'type': 'field_select', 'default': 'A'}",
                    "]",
                    "def describe_config(params, context):",
                    "    return {'schema_version': 'stdio_demo.config.v1', 'summary': {'field': params.get('field', '')}}",
                    "def run(input_data, params, context):",
                    "    return {'ok': True, 'output': input_data}",
                ]),
                encoding="utf-8",
            )

            schema = worker.handle_request(request("get_plugin_schema", {
                "plugin_id": "plugin.stdio_demo",
                "plugins_dir": temp_dir,
                "preview_headers": ["A"],
            }))
            described = worker.handle_request(request("describe_plugin_config", {
                "plugin_id": "plugin.stdio_demo",
                "plugins_dir": temp_dir,
                "input_table": {"headers": ["A"], "rows": [["x"]]},
            }))

        self.assertTrue(schema["ok"])
        self.assertEqual(
            schema["result"]["schema"]["parameter_metadata"]["layout_index"]["schema_version"],
            "plugin_parameter_layout.v1",
        )
        self.assertEqual(
            schema["result"]["schema"]["parameter_metadata"]["ui_hints"]["schema_version"],
            "plugin_parameter_ui_hints.v1",
        )
        self.assertEqual(
            schema["result"]["schema"]["parameter_metadata"]["layout_index"]["field_order"],
            ["params.field"],
        )
        self.assertTrue(described["ok"])
        self.assertEqual(
            described["result"]["parameter_metadata"]["layout_index"]["schema_version"],
            "plugin_parameter_layout.v1",
        )
        self.assertEqual(
            described["result"]["parameter_metadata"]["ui_hints"]["schema_version"],
            "plugin_parameter_ui_hints.v1",
        )
        self.assertEqual(
            described["result"]["parameter_metadata"]["layout_index"]["field_order"],
            ["params.field"],
        )
        self.assertEqual(described["result"]["layout"]["schema_version"], "plugin_config_layout.v1")
        self.assertEqual(described["result"]["layout"]["default_view_id"], "plugin.params")
        self.assertIn("plugin.params", described["result"]["layout"]["view_order"])
        self.assertEqual(described["result"]["ui_hints"]["schema_version"], "plugin_config_ui_hints.v1")
        self.assertEqual(described["result"]["ui_hints"]["parameter_field_hints"]["schema_version"], "plugin_parameter_ui_hints.v1")
        self.assertEqual(described["result"]["ui_hints"]["view_hints"]["plugin.params"]["kind"], "form")
        view_by_id = {view["view_id"]: view for view in described["result"]["views"]}
        self.assertIn("plugin.parameter_metadata", view_by_id)
        self.assertEqual(view_by_id["plugin.parameter_metadata"]["kind"], "summary")
        self.assertEqual(view_by_id["plugin.parameter_metadata"]["summary"]["field_count"], 1)

    def test_describe_node_config_context_exposes_filter_shared_state(self):
        worker = StdioWorker()

        response = worker.handle_request(request("describe_node_config_context", {
            "node": {
                "node_type_id": "core.filter",
                "enabled": True,
                "config": {
                    "extra_tables": ["lookup", "中转:cached"],
                    "output_fields": ["当前表.Code", "lookup.Name", "中转:cached.Value"],
                },
            },
            "preview_headers": ["Code"],
            "table_names": ["lookup"],
            "table_columns": {"lookup": ["Code", "Name"]},
            "transit_context": {"transit_tables": {"cached": {"headers": ["Value"]}}},
        }))

        self.assertTrue(response["ok"])
        context = response["result"]["shared_config_context"]
        self.assertEqual(context["schema_version"], "filter_config_context.v1")
        self.assertEqual(context["service"]["schema_version"], "advanced_filter_service.v1")
        self.assertEqual(context["command_schema"]["schema_version"], "advanced_filter_command.v1")
        self.assertEqual(context["layout"]["schema_version"], "advanced_filter_layout.v1")
        self.assertEqual(context["ui_hints"]["schema_version"], "advanced_filter_ui_hints.v1")
        self.assertEqual(context["layout"]["default_section_id"], "conditions")
        self.assertEqual(context["command_schema"]["commands"]["build_preview"]["section_id"], "preview")
        self.assertEqual(context["command_schema"]["commands"]["save_preview_to_table"]["section_id"], "preview")
        self.assertEqual(context["command_schema"]["commands"]["save_preview_to_table"]["result"], "advanced_filter_save_result")
        self.assertEqual(context["selected_tables"], ["当前表", "lookup", "中转:cached"])
        self.assertEqual(
            context["available_fields"],
            ["当前表.Code", "lookup.Code", "lookup.Name", "中转:cached.Value"],
        )
        self.assertEqual(context["field_state"]["first_external"], "lookup.Code")
        self.assertIn("实际输出字段", context["output_text"])
        self.assertEqual(response["result"]["shared_config_sections"][0]["source"], "filter_config_context.v1")

    def test_apply_node_config_command_updates_filter_config_over_stdio(self):
        worker = StdioWorker()

        response = worker.handle_request(request("apply_node_config_command", {
            "node_type_id": "core.filter",
            "config": {"extra_tables": ["lookup"], "output_fields": []},
            "command": {"type": "add_all_output_fields"},
            "preview_headers": ["Code"],
            "table_names": ["lookup"],
            "table_columns": {"lookup": ["Code", "Name"]},
        }))

        self.assertTrue(response["ok"])
        result = response["result"]
        self.assertEqual(result["schema_version"], "filter_config_command_result.v1")
        self.assertEqual(result["config"]["output_fields"], ["当前表.Code", "lookup.Code", "lookup.Name"])
        self.assertEqual(result["shared_config_context"]["selected_tables"], ["当前表", "lookup"])
        self.assertIn("实际输出字段", result["shared_config_context"]["output_text"])

    def test_filter_config_template_file_commands_work_over_stdio(self):
        worker = StdioWorker()

        with TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "filter_node_template.json")
            saved = worker.handle_request(request("apply_node_config_command", {
                "node_type_id": "core.filter",
                "config": {
                    "extra_tables": ["lookup"],
                    "conditions": [{
                        "field": "当前表.Code",
                        "op": "等于",
                        "value_source": "字段值",
                        "value": "lookup.Code",
                    }],
                    "join_rules": [{
                        "left": "当前表.Code",
                        "op": "等于",
                        "right_table": "lookup",
                        "right": "lookup.Code",
                    }],
                    "output_fields": ["lookup.Name"],
                    "remove_duplicates": True,
                },
                "command": {"type": "save_template_file", "path": path},
                "preview_headers": ["Code"],
                "table_names": ["lookup"],
                "table_columns": {"lookup": ["Code", "Name"]},
            }))
            loaded = worker.handle_request(request("apply_node_config_command", {
                "node_type_id": "core.filter",
                "config": {},
                "command": {"type": "load_template_file", "path": path},
                "preview_headers": ["Code"],
                "table_names": ["lookup"],
                "table_columns": {"lookup": ["Code", "Name"]},
            }))

        self.assertTrue(saved["ok"])
        self.assertEqual(saved["result"]["template_file"]["schema_version"], "filter_config_template_file.v1")
        self.assertEqual(saved["result"]["template_file"]["template"]["schema_version"], "filter_config_template.v1")
        self.assertTrue(loaded["ok"])
        self.assertEqual(loaded["result"]["config"]["extra_tables"], ["lookup"])
        self.assertEqual(loaded["result"]["config"]["output_fields"], ["lookup.Name"])
        self.assertTrue(loaded["result"]["config"]["remove_duplicates"])
        self.assertEqual(loaded["result"]["config"]["conditions"][0]["value_source"], "字段值")

    def test_resolve_node_config_options_returns_filter_candidates_over_stdio(self):
        worker = StdioWorker()

        response = worker.handle_request(request("resolve_node_config_options", {
            "node_type_id": "core.filter",
            "config": {"extra_tables": ["lookup"]},
            "field_key": "join_rules.right",
            "current_values": {"right_table": "lookup"},
            "preview_headers": ["Code"],
            "table_names": ["lookup"],
            "table_columns": {"lookup": ["Code", "Name"]},
        }))

        self.assertTrue(response["ok"])
        result = response["result"]
        self.assertEqual(result["schema_version"], "filter_config_options.v1")
        self.assertEqual(result["source"], "table_fields")
        self.assertEqual(result["choices"], ["lookup.Code", "lookup.Name"])

    def test_make_default_node_and_validate_plan(self):
        worker = StdioWorker()

        made = worker.handle_request(request("make_default_node", {
            "node_type_id": "core.new_columns",
            "preview_headers": ["A"],
            "include_legacy_type": False,
        }))
        validation = worker.handle_request(request("validate_plan", {
            "plan": {
                "nodes": [
                    {"type": "新建列", "enabled": True, "config": {"columns_text": "B"}},
                    {"type": "插件节点", "enabled": True, "config": {}},
                ]
            }
        }))

        self.assertTrue(made["ok"])
        self.assertEqual(made["result"]["node"]["node_type_id"], "core.new_columns")
        self.assertNotIn("type", made["result"]["node"])
        self.assertTrue(validation["ok"])
        self.assertFalse(validation["result"]["ok"])
        self.assertEqual(validation["result"]["issues"][0]["code"], "unsupported_node")

    def test_import_table_file_uses_backend_facade(self):
        worker = StdioWorker()
        with TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "rows.csv"
            csv_path.write_text("A,B\na,1\nb,2\n", encoding="utf-8")

            response = worker.handle_request(request("import_table_file", {"path": str(csv_path)}))

        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["table"]["headers"], ["A", "B"])
        self.assertEqual(response["result"]["table"]["rows"], [["a", "1"], ["b", "2"]])

    def test_data_source_table_actions_use_headless_service(self):
        worker = StdioWorker()

        parsed = worker.handle_request(request("parse_clipboard_table", {
            "text": "A\tB\nx\ty\nz\tw",
            "first_row_header": True,
        }))
        table = parsed["result"]["table"]
        patched = worker.handle_request(request("patch_table_cell", {
            "table": table,
            "row": 1,
            "column": 1,
            "value": "updated",
        }))
        searched = worker.handle_request(request("search_table", {
            "table": patched["result"]["table"],
            "keyword": "updated",
        }))
        navigation = worker.handle_request(request("build_table_search_navigation", {
            "matches": searched["result"]["matches"],
            "current_index": 0,
            "offset": 0,
        }))
        save_modes = worker.handle_request(request("describe_table_save_modes"))
        normalized_mode = worker.handle_request(request("normalize_table_save_mode", {
            "mode": "自动加时间戳",
        }))
        state = worker.handle_request(request("build_data_source_state", {
            "table": patched["result"]["table"],
            "source": {"type": "clipboard"},
            "dirty": True,
            "display_name": "临时输入",
        }))
        actions = worker.handle_request(request("describe_data_source_actions", {
            "table": patched["result"]["table"],
            "source": {"type": "clipboard"},
            "dirty": True,
        }))
        panel = worker.handle_request(request("build_data_source_panel_state", {
            "table": patched["result"]["table"],
            "source": {"type": "sqlite", "db_path": "input.db", "table_name": "orders"},
            "dirty": True,
            "display_name": "临时输入",
            "partial": True,
            "page_info": {"offset": 1, "limit": 2, "has_more": True},
            "search_navigation": searched["result"]["navigation"],
        }))
        manager = worker.handle_request(request("build_data_source_manager_state", {
            "table": patched["result"]["table"],
            "source": {"type": "sqlite", "db_path": "input.db", "table_name": "orders"},
            "dirty": True,
            "display_name": "临时输入",
            "partial": True,
            "page_info": {"offset": 1, "limit": 2, "has_more": True},
            "search_navigation": searched["result"]["navigation"],
            "db_path": "input.db",
            "table_names": ["orders", "archive"],
            "selected_table": "orders",
        }))
        service_desc = worker.handle_request(request("describe_data_source_service"))

        self.assertTrue(parsed["ok"])
        self.assertEqual(table["headers"], ["A", "B"])
        self.assertTrue(patched["ok"])
        self.assertEqual(patched["result"]["table"]["rows"][1][1], "updated")
        self.assertEqual(searched["result"]["count"], 1)
        self.assertEqual(searched["result"]["matches"][0]["row"], 1)
        self.assertEqual(searched["result"]["navigation"]["current_cell"], {"row": 1, "column": 1})
        self.assertEqual(navigation["result"]["navigation"]["status_text"], "1/1")
        self.assertEqual([item["id"] for item in save_modes["result"]["modes"]], ["replace", "timestamp", "fail", "append"])
        self.assertEqual(save_modes["result"]["schema_version"], "table_save_modes.v1")
        self.assertEqual(normalized_mode["result"]["mode"], "timestamp")
        self.assertEqual(state["result"]["state"]["schema_version"], "data_source_state.v1")
        self.assertTrue(state["result"]["state"]["action_state"]["actions"]["patch_cell"]["enabled"])
        self.assertEqual(state["result"]["state"]["display_name"], "临时输入")
        self.assertTrue(state["result"]["state"]["dirty"])
        self.assertTrue(actions["result"]["actions"]["save_sqlite"]["enabled"])
        self.assertFalse(actions["result"]["actions"]["delete_sqlite"]["enabled"])
        self.assertEqual(actions["result"]["action_schema"]["actions"]["patch_cell"]["engine_action"], "patch_table_cell")
        self.assertEqual(panel["result"]["panel_state"]["schema_version"], "data_source_panel_state.v1")
        self.assertEqual(panel["result"]["panel_state"]["view_state"]["search"]["current_cell"], {"row": 1, "column": 1})
        self.assertEqual(panel["result"]["panel_state"]["view_state"]["page_status_text"], "分页预览：第 2-3 行，每页 2，还有下一页")
        self.assertTrue(panel["result"]["panel_state"]["view_state"]["page_controls"]["page_size_enabled"])
        self.assertTrue(panel["result"]["panel_state"]["view_state"]["page_controls"]["prev_enabled"])
        self.assertTrue(panel["result"]["panel_state"]["view_state"]["page_controls"]["next_enabled"])
        self.assertTrue(panel["result"]["panel_state"]["view_state"]["page_controls"]["load_full_enabled"])
        self.assertIn("describe_data_source_service", panel["result"]["panel_state"]["service"]["action_ids"])
        self.assertEqual(manager["result"]["manager_state"]["schema_version"], "data_source_manager_state.v1")
        self.assertEqual(manager["result"]["manager_state"]["panel_state"]["schema_version"], "data_source_panel_state.v1")
        self.assertEqual(manager["result"]["manager_state"]["layout"]["schema_version"], "data_source_manager_layout.v1")
        self.assertIn("table_loader", manager["result"]["manager_state"]["layout"]["section_order"])
        self.assertEqual(manager["result"]["manager_state"]["ui_hints"]["schema_version"], "data_source_manager_ui_hints.v1")
        self.assertEqual(manager["result"]["manager_state"]["ui_hints"]["action_prominence"]["apply_to_workflow"], "primary")
        self.assertEqual(manager["result"]["manager_state"]["source_controls"]["table_names"], ["orders", "archive"])
        self.assertTrue(manager["result"]["manager_state"]["source_controls"]["load_enabled"])
        self.assertIn("build_data_source_manager_state", manager["result"]["manager_state"]["service"]["action_ids"])
        self.assertTrue(service_desc["ok"])
        self.assertEqual(service_desc["result"]["schema_version"], "data_source_service.v1")
        self.assertEqual(service_desc["result"]["data_actions"]["save_sqlite"]["engine_action"], "save_table")
        self.assertEqual(service_desc["result"]["table_actions"]["load_table"]["engine_action"], "load_table")
        self.assertEqual(
            service_desc["result"]["table_actions"]["create_table_handle"]["result"],
            "table_handle",
        )
        self.assertIn("get_table_handle_page", service_desc["result"]["action_schema"]["actions"])
        self.assertIn("build_data_source_manager_state", service_desc["result"]["actions"])
        self.assertEqual(
            service_desc["result"]["result_schemas"]["data_source_manager_state"]["schema_version"],
            "data_source_manager_state.v1",
        )
        self.assertEqual(
            service_desc["result"]["result_schemas"]["data_source_manager_layout"]["schema_version"],
            "data_source_manager_layout.v1",
        )
        self.assertEqual(
            service_desc["result"]["result_schemas"]["data_source_manager_ui_hints"]["schema_version"],
            "data_source_manager_ui_hints.v1",
        )
        self.assertTrue(service_desc["result"]["capabilities"]["sqlite_save"])

    def test_data_source_save_and_delete_table_actions(self):
        worker = StdioWorker()
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "input.db")
            table = {"type": "table", "headers": ["id", "name"], "rows": [["1", "Alice"]]}

            saved = worker.handle_request(request("save_table", {
                "table": table,
                "db_path": db_path,
                "table_name": "orders",
                "mode": "replace",
            }))
            loaded = worker.handle_request(request("load_table", {
                "db_path": db_path,
                "table_name": "orders",
            }))
            refused = worker.handle_request(request("delete_table", {
                "db_path": db_path,
                "table_name": "orders",
                "backup": False,
                "confirmed": False,
            }))
            deleted = worker.handle_request(request("delete_table", {
                "db_path": db_path,
                "table_name": "orders",
                "backup": False,
                "confirmed": True,
            }))
            listed = worker.handle_request(request("list_tables", {"db_path": db_path}))

        table_names = [
            item.get("name") if isinstance(item, dict) else str(item)
            for item in listed["result"]["tables"]
        ]
        self.assertTrue(saved["ok"])
        self.assertTrue(saved["result"]["ok"])
        self.assertEqual(saved["result"]["source"]["table_name"], "orders")
        self.assertEqual(loaded["result"]["table"]["rows"], [["1", "Alice"]])
        self.assertTrue(refused["ok"])
        self.assertFalse(refused["result"]["ok"])
        self.assertEqual(refused["result"]["issues"][0]["code"], "delete_not_confirmed")
        self.assertTrue(deleted["result"]["ok"])
        self.assertNotIn("orders", table_names)

    def test_preview_plan_uses_protocol_input_data_name(self):
        worker = StdioWorker()
        response = worker.handle_request(request("preview_plan", {
            "plan": {
                "nodes": [
                    {
                        "node_type_id": "core.new_columns",
                        "enabled": True,
                        "config": {"columns_text": "B=b", "value_mode": "按列配置值"},
                    }
                ]
            },
            "input_data": {"type": "table", "headers": ["A"], "rows": [["a"]]},
        }))

        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["table"]["headers"], ["A", "B"])
        self.assertEqual(response["result"]["table"]["rows"], [["a", "b"]])
        self.assertEqual(response["result"]["steps"], 1)

    def test_run_plan_returns_plan_validation_error_response(self):
        worker = StdioWorker()
        response = worker.handle_request(request("run_plan", {
            "plan": {"nodes": [{"type": "插件节点", "enabled": True, "config": {}}]},
            "input_data": {"type": "table", "headers": [], "rows": []},
        }))

        self.assertFalse(response["ok"])
        self.assertEqual(response["errors"][0]["code"], "plan_validation_error")
        self.assertEqual(response["errors"][0]["issues"][0]["node_type"], "插件节点")

    def test_request_validation_errors_are_response_objects(self):
        worker = StdioWorker()

        bad_api = worker.handle_request({"request_id": "bad", "api_version": "2.0", "action": "list_node_types", "payload": {}})
        bad_payload = worker.handle_request({"request_id": "bad2", "api_version": "1.0", "action": "list_node_types", "payload": []})
        unknown = worker.handle_request(request("does_not_exist"))

        self.assertFalse(bad_api["ok"])
        self.assertEqual(bad_api["errors"][0]["code"], "unsupported_api_version")
        self.assertFalse(bad_payload["ok"])
        self.assertEqual(bad_payload["errors"][0]["code"], "invalid_payload")
        self.assertFalse(unknown["ok"])
        self.assertEqual(unknown["errors"][0]["code"], "runtime_error")

    def test_iter_json_lines_handles_valid_and_invalid_lines(self):
        input_stream = io.StringIO(
            json.dumps(request("list_node_types", {"include_unsupported": False}), ensure_ascii=False)
            + "\n"
            + "{bad json}\n"
        )
        output_stream = io.StringIO()

        iter_json_lines(input_stream, output_stream, worker=StdioWorker())

        lines = [json.loads(line) for line in output_stream.getvalue().splitlines()]
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0]["ok"])
        self.assertFalse(lines[1]["ok"])
        self.assertEqual(lines[1]["errors"][0]["code"], "invalid_json")


if __name__ == "__main__":
    unittest.main()
