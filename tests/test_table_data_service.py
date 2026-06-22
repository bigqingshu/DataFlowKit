# -*- coding: utf-8 -*-
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.headless import HeadlessWorkflowEngine
from engine.stdio_worker import StdioWorker
from engine.workflow_services import WorkflowServices


def request(action, payload=None, request_id="req1"):
    return {
        "request_id": request_id,
        "api_version": "1.0",
        "action": action,
        "payload": payload or {},
    }


class TableDataServiceTests(unittest.TestCase):
    def test_loads_file_table_and_pages_inline_table(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rows.json"
            path.write_text(json.dumps([
                {"A": "a", "B": 1},
                {"A": "b", "B": 2},
            ], ensure_ascii=False), encoding="utf-8")
            engine = HeadlessWorkflowEngine()

            loaded = engine.load_table({"type": "file", "path": str(path)})
            page = engine.get_table_page(
                {"headers": ["A"], "rows": [["r1"], ["r2"], ["r3"]]},
                limit=2,
                offset=1,
            )

            self.assertTrue(loaded["ok"])
            self.assertEqual(loaded["table"]["headers"], ["A", "B"])
            self.assertEqual(loaded["table"]["rows"][0], ["a", 1])
            self.assertEqual(page["table"]["rows"], [["r2"], ["r3"]])
            self.assertFalse(page["page"]["has_more"])

    def test_lists_and_loads_sqlite_tables(self):
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "tables.db")
            services = WorkflowServices(db_path=db_path)
            services.write_table(
                "结果表",
                {"headers": ["A"], "rows": [["a"], ["b"]]},
                mode="replace",
            )
            engine = HeadlessWorkflowEngine(services=services)

            listed = engine.list_tables()
            loaded = engine.load_table({"type": "sqlite", "table_name": "结果表", "limit": 1})

            self.assertTrue(listed["ok"])
            self.assertIn("结果表", listed["tables"])
            self.assertTrue(loaded["ok"])
            self.assertEqual(loaded["table"]["headers"], ["A"])
            self.assertEqual(loaded["table"]["rows"], [["a"]])
            self.assertEqual(loaded["page"]["limit"], 1)

    def test_stdio_worker_exposes_table_actions(self):
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "stdio.db")
            services = WorkflowServices(db_path=db_path)
            services.write_table("T", {"headers": ["A"], "rows": [["x"]]}, mode="replace")
            worker = StdioWorker(HeadlessWorkflowEngine(services=services))

            listed = worker.handle_request(request("list_tables", {"db_path": db_path}))
            loaded = worker.handle_request(request("load_table", {
                "source": {"type": "sqlite", "table_name": "T"},
                "db_path": db_path,
            }))
            page = worker.handle_request(request("get_table_page", {
                "table": {"headers": ["A"], "rows": [["1"], ["2"]]},
                "limit": 1,
                "offset": 1,
            }))

            self.assertTrue(listed["ok"])
            self.assertEqual(listed["result"]["tables"], ["T"])
            self.assertTrue(loaded["result"]["ok"])
            self.assertEqual(loaded["result"]["table"]["rows"], [["x"]])
            self.assertEqual(page["result"]["table"]["rows"], [["2"]])


if __name__ == "__main__":
    unittest.main()
