# -*- coding: utf-8 -*-
import io
import json
import unittest

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
        target_fields = [
            field
            for group in schema["result"]["form"]["groups"]
            for field in group["fields"]
            if field["key"] == "target_field"
        ]
        self.assertEqual(target_fields[0]["type"], "field_select")
        self.assertEqual(target_fields[0]["choices"], ["A", "B"])

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
