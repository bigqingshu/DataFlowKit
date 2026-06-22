# -*- coding: utf-8 -*-
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine.headless import HeadlessWorkflowEngine
from engine.workflow_services import WorkflowServices


class HeadlessSaveTransitNodeTests(unittest.TestCase):
    def test_preview_writes_memory_transit_without_sqlite_side_effect(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            db_path = str(Path(temp_dir) / "preview.db")
            engine = HeadlessWorkflowEngine(services=WorkflowServices(db_path=db_path))
            plan = {
                "nodes": [{
                    "node_type_id": "core.save_transit",
                    "enabled": True,
                    "config": {
                        "transit_name": "副表",
                        "save_memory": True,
                        "save_sqlite": True,
                        "sqlite_table": "副表_sql",
                    },
                }],
                "headers": ["A"],
                "rows": [["x"], ["y", "extra"]],
            }

            validation = engine.validate_plan(plan)
            result = engine.preview_plan(plan)

        self.assertTrue(validation["ok"])
        self.assertIn("副表", result.context["transit_tables"])
        self.assertEqual(result.context["transit_tables"]["副表"]["rows"], [["x"], ["y"]])
        self.assertFalse(os.path.exists(db_path))
        self.assertIn("SQLite表：预览模式未写入", result.logs[0])

    def test_execute_writes_save_transit_sqlite_through_services(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            db_path = str(Path(temp_dir) / "run.db")
            engine = HeadlessWorkflowEngine(services=WorkflowServices(db_path=db_path))
            plan = {
                "nodes": [{
                    "node_type_id": "core.save_transit",
                    "enabled": True,
                    "config": {
                        "transit_name": "副表",
                        "save_memory": False,
                        "save_sqlite": True,
                        "sqlite_table": "副表_sql",
                        "sqlite_mode": "覆盖同名表",
                    },
                }],
                "headers": ["A"],
                "rows": [["x"]],
            }

            result = engine.run_plan(plan, execute_actions=True)
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute('SELECT A FROM "副表_sql"').fetchall()
            finally:
                conn.close()

        self.assertEqual(rows, [("x",)])
        self.assertIn("SQLite表：副表_sql", result.logs[0])


if __name__ == "__main__":
    unittest.main()
