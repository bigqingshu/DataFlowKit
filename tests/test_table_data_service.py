# -*- coding: utf-8 -*-
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from db.table_manager import TableAccessManager
from engine.headless import HeadlessWorkflowEngine
from engine.stdio_worker import StdioWorker
from engine.table_data_service import (
    TableDataService,
    build_data_source_state,
    normalize_table_headers,
    parse_clipboard_table,
    patch_table_cell,
    promote_first_row_to_headers,
    search_table,
)
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

    def test_table_handles_page_and_release_inline_tables(self):
        engine = HeadlessWorkflowEngine()

        created = engine.create_table_handle(
            {"type": "table", "headers": ["A"], "rows": [["1"], ["2"], ["3"]]},
            limit=2,
        )
        page = engine.get_table_page(created["handle"], limit=1, offset=2)
        handles = engine.list_table_handles()
        released = engine.release_table_handle(created["handle"])
        missing = engine.get_table_handle_page(created["handle"], limit=1)

        self.assertTrue(created["ok"])
        self.assertEqual(created["schema"]["row_count"], 3)
        self.assertEqual(created["table"]["rows"], [["1"], ["2"]])
        self.assertEqual(page["table"]["rows"], [["3"]])
        self.assertEqual(handles["count"], 1)
        self.assertTrue(released["released"])
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["issues"][0]["code"], "table_handle_not_found")

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

    def test_stdio_worker_exposes_table_handle_actions(self):
        worker = StdioWorker()

        created = worker.handle_request(request("create_table_handle", {
            "table": {"type": "table", "headers": ["A"], "rows": [["1"], ["2"]]},
            "limit": 1,
        }))
        handle = created["result"]["handle"]
        page = worker.handle_request(request("get_table_handle_page", {
            "handle": handle,
            "limit": 1,
            "offset": 1,
        }))
        listed = worker.handle_request(request("list_table_handles"))
        released = worker.handle_request(request("release_table_handle", {"handle": handle}))

        self.assertTrue(created["ok"])
        self.assertEqual(created["result"]["table"]["rows"], [["1"]])
        self.assertEqual(page["result"]["table"]["rows"], [["2"]])
        self.assertEqual(listed["result"]["count"], 1)
        self.assertTrue(released["result"]["released"])

    def test_parse_clipboard_table_normalizes_headers_and_rows(self):
        table = parse_clipboard_table(" A\tA\t\n x\t y\t z\n", first_row_header=True)

        self.assertEqual(table["headers"], ["A", "A_2", "列3"])
        self.assertEqual(table["rows"], [["x", "y", "z"]])
        self.assertEqual(table["meta"]["delimiter"], "tab")

    def test_table_editing_helpers_are_ui_free(self):
        table = {
            "headers": ["old1", "old2"],
            "rows": [["H1", "H1"], ["a", "b"]],
        }

        promoted = promote_first_row_to_headers(table)
        patched = patch_table_cell(promoted, row=0, column=1, value="changed")
        matches = search_table(patched, "chan")
        state = build_data_source_state(
            patched,
            source={"type": "memory"},
            dirty=True,
            display_name="demo",
        )

        self.assertEqual(promoted["headers"], ["H1", "H1_2"])
        self.assertEqual(patched["rows"], [["a", "changed"]])
        self.assertEqual(matches[0]["cells"][0]["header"], "H1_2")
        self.assertTrue(state["dirty"])
        self.assertEqual(state["row_count"], 1)
        self.assertEqual(normalize_table_headers(["", "A", "A"]), ["列1", "A", "A_2"])

    def test_service_saves_and_deletes_sqlite_table_with_confirmation(self):
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "data.db")
            service = TableDataService()
            table = {"headers": ["A"], "rows": [["x"]]}

            saved = service.save_table(table, db_path=db_path, table_name="input_data", mode="replace")
            manager = TableAccessManager(db_path)
            saved_rows = manager.read_table("input_data")["rows"]
            blocked = service.delete_table(db_path=db_path, table_name="input_data", confirmed=False)
            deleted = service.delete_table(db_path=db_path, table_name="input_data", backup=True, confirmed=True)

            self.assertTrue(saved["ok"])
            self.assertEqual(saved["source"]["table_name"], "input_data")
            self.assertEqual(saved_rows, [["x"]])
            self.assertFalse(blocked["ok"])
            self.assertEqual(blocked["issues"][0]["code"], "delete_not_confirmed")
            self.assertTrue(deleted["ok"])
            self.assertNotIn("input_data", manager.list_tables())
            self.assertIn(deleted["backup_table"], manager.list_tables())

    def test_service_returns_issues_for_invalid_clipboard(self):
        result = TableDataService().parse_clipboard_table("   ")

        self.assertFalse(result["ok"])
        self.assertEqual(result["issues"][0]["code"], "parse_clipboard_table_failed")


if __name__ == "__main__":
    unittest.main()
