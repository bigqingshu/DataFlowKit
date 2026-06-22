# -*- coding: utf-8 -*-
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.plan_io import build_plan_document, list_plan_templates, load_plan, save_plan


class EnginePlanIoTests(unittest.TestCase):
    def test_list_load_build_and_save_plan(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan_path = root / "demo.json"
            other_path = root / "skip.txt"
            plan_path.write_text(json.dumps({
                "template_type": "workflow_plan",
                "version": "1.0",
                "plan_name": "demo",
                "nodes": [],
            }, ensure_ascii=False), encoding="utf-8")
            other_path.write_text("x", encoding="utf-8")

            templates = list_plan_templates(root)
            loaded = load_plan(plan_path)
            document = build_plan_document(
                loaded["plan"],
                headers=["A"],
                rows=[["a"]],
                output_mode="输出到主界面预览区",
                output_table="结果",
                backup_before_overwrite=False,
                db_path="demo.db",
                output_path="demo.xlsx",
            )
            saved_path = root / "saved.json"
            saved = save_plan(saved_path, document)

            self.assertEqual(len(templates), 1)
            self.assertEqual(templates[0]["name"], "demo")
            self.assertEqual(loaded["plan"]["plan_name"], "demo")
            self.assertEqual(document["headers"], ["A"])
            self.assertEqual(document["rows"], [["a"]])
            self.assertFalse(document["backup_before_overwrite"])
            self.assertEqual(document["db_path"], "demo.db")
            self.assertEqual(document["output_path"], "demo.xlsx")
            self.assertTrue(saved["ok"])
            self.assertEqual(json.loads(saved_path.read_text(encoding="utf-8"))["output_table"], "结果")

    def test_load_plan_rejects_non_object_json(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.json"
            path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "JSON object"):
                load_plan(path)


if __name__ == "__main__":
    unittest.main()
