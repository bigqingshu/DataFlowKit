# -*- coding: utf-8 -*-
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.headless import HeadlessWorkflowEngine
from engine.stdio_worker import StdioWorker


def request(action, payload=None, request_id="req1"):
    return {
        "request_id": request_id,
        "api_version": "1.0",
        "action": action,
        "payload": payload or {},
    }


class PlanTemplateServiceTests(unittest.TestCase):
    def test_headless_service_lists_loads_migrates_and_saves_template(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "legacy.json"
            source_path.write_text(json.dumps({
                "plan_name": "legacy",
                "nodes": [
                    {"type": "新建列", "enabled": True, "config": {"columns_text": "B=b"}},
                ],
            }, ensure_ascii=False), encoding="utf-8")

            counter = iter(["node_1", "node_2", "node_3"])
            engine = HeadlessWorkflowEngine(node_id_factory=lambda: next(counter))

            listed = engine.list_plan_templates(root)
            loaded = engine.load_plan_template(source_path)
            invalid = engine.validate_plan_template({"template_type": "bad", "nodes": []})
            saved_path = root / "saved.json"
            saved = engine.save_plan_template(
                saved_path,
                {"nodes": [{"type": "新建列", "enabled": True, "config": {"columns_text": "C=c"}}]},
                headers=["A"],
                rows=[["a"]],
                output_mode="输出到主界面预览区",
                output_table="结果",
                backup_before_overwrite=False,
                db_path="demo.db",
                output_path="demo.xlsx",
                input_source={"type": "sqlite", "db_path": "input.db", "table_name": "orders"},
                input_db_path="input.db",
            )

            self.assertTrue(listed["ok"])
            self.assertEqual([item["name"] for item in listed["templates"]], ["legacy"])
            self.assertTrue(loaded["ok"])
            self.assertTrue(loaded["migration"]["changed"])
            self.assertEqual(loaded["plan"]["template_type"], "workflow_plan")
            self.assertEqual(loaded["plan"]["nodes"][0]["node_type_id"], "core.new_columns")
            self.assertFalse(invalid["ok"])
            self.assertEqual(invalid["issues"][0]["code"], "invalid_template_type")
            self.assertTrue(saved["ok"])
            saved_data = json.loads(saved_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_data["template_type"], "workflow_plan")
            self.assertEqual(saved_data["headers"], ["A"])
            self.assertEqual(saved_data["rows"], [["a"]])
            self.assertEqual(saved_data["nodes"][0]["node_type_id"], "core.new_columns")
            self.assertEqual(saved_data["db_path"], "demo.db")
            self.assertEqual(saved_data["output_path"], "demo.xlsx")
            self.assertEqual(saved_data["input_source"]["table_name"], "orders")
            self.assertEqual(saved_data["input_db_path"], "input.db")

    def test_stdio_worker_exposes_plan_template_actions(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "demo.json"
            target_path = root / "saved.json"
            source_path.write_text(json.dumps({
                "template_type": "workflow_plan",
                "plan_name": "demo",
                "nodes": [],
            }, ensure_ascii=False), encoding="utf-8")

            worker = StdioWorker(HeadlessWorkflowEngine(node_id_factory=lambda: "node_stdio"))

            listed = worker.handle_request(request("list_plan_templates", {"plan_dir": str(root)}))
            loaded = worker.handle_request(request("load_plan_template", {"path": str(source_path)}))
            validated = worker.handle_request(request("validate_plan_template", {"plan": {"template_type": "bad", "nodes": []}}))
            saved = worker.handle_request(request("save_plan_template", {
                "path": str(target_path),
                "plan": {"nodes": []},
                "headers": ["A"],
                "rows": [["a"]],
                "input_source": {"type": "sqlite", "db_path": "input.db", "table_name": "orders"},
                "input_db_path": "input.db",
            }))

            self.assertTrue(listed["ok"])
            self.assertEqual(listed["result"]["templates"][0]["name"], "demo")
            self.assertTrue(loaded["ok"])
            self.assertTrue(loaded["result"]["ok"])
            self.assertEqual(loaded["result"]["plan"]["plan_name"], "demo")
            self.assertTrue(validated["ok"])
            self.assertFalse(validated["result"]["ok"])
            self.assertTrue(saved["ok"])
            self.assertTrue(saved["result"]["ok"])
            self.assertTrue(target_path.exists())
            saved_data = json.loads(target_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_data["input_source"]["table_name"], "orders")
            self.assertEqual(saved_data["input_db_path"], "input.db")


if __name__ == "__main__":
    unittest.main()
