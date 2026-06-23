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
        state = worker.handle_request(request("build_data_source_state", {
            "table": patched["result"]["table"],
            "source": {"type": "clipboard"},
            "dirty": True,
            "display_name": "临时输入",
        }))

        self.assertTrue(parsed["ok"])
        self.assertEqual(table["headers"], ["A", "B"])
        self.assertTrue(patched["ok"])
        self.assertEqual(patched["result"]["table"]["rows"][1][1], "updated")
        self.assertEqual(searched["result"]["count"], 1)
        self.assertEqual(searched["result"]["matches"][0]["row"], 1)
        self.assertEqual(state["result"]["state"]["display_name"], "临时输入")
        self.assertTrue(state["result"]["state"]["dirty"])

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
