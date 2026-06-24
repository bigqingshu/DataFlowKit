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
    build_search_navigation,
    build_data_source_state,
    describe_save_modes,
    flatten_search_matches,
    normalize_table_headers,
    normalize_save_mode,
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
            actions = worker.handle_request(request("describe_data_source_actions", {
                "table": {"headers": ["A"], "rows": [["1"]]},
                "source": {"type": "sqlite", "db_path": db_path, "table_name": "T"},
            }))

            self.assertTrue(listed["ok"])
            self.assertEqual(listed["result"]["tables"], ["T"])
            self.assertTrue(loaded["result"]["ok"])
            self.assertEqual(loaded["result"]["table"]["rows"], [["x"]])
            self.assertEqual(page["result"]["table"]["rows"], [["2"]])
            self.assertTrue(actions["result"]["actions"]["delete_sqlite"]["enabled"])
            self.assertTrue(actions["result"]["action_state"]["is_sqlite_source"])

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
        sqlite_actions = TableDataService().describe_data_source_actions(
            patched,
            source={"type": "sqlite", "db_path": "input.db", "table_name": "demo"},
            dirty=False,
        )
        service_desc = TableDataService().describe_data_source_service()
        panel = TableDataService().build_data_source_panel_state(
            patched,
            source={"type": "sqlite", "db_path": "input.db", "table_name": "demo"},
            dirty=True,
            display_name="demo",
            partial=True,
            page_info={"offset": 10, "limit": 50, "has_more": True},
            search_navigation={"keyword": "chan", "status_text": "1/1", "current_cell": {"row": 0, "column": 1}, "highlighted_rows": [0]},
        )

        self.assertEqual(promoted["headers"], ["H1", "H1_2"])
        self.assertEqual(patched["rows"], [["a", "changed"]])
        self.assertEqual(matches[0]["cells"][0]["header"], "H1_2")
        self.assertEqual(state["schema_version"], "data_source_state.v1")
        self.assertEqual(state["table"], {"type": "table", "headers": ["H1", "H1_2"], "rows": [["a", "changed"]]})
        self.assertEqual(state["shape"], {"rows": 1, "columns": 2})
        self.assertTrue(state["dirty"])
        self.assertEqual(state["row_count"], 1)
        self.assertTrue(state["action_state"]["actions"]["patch_cell"]["enabled"])
        self.assertTrue(state["action_state"]["actions"]["save_sqlite"]["enabled"])
        self.assertFalse(state["action_state"]["actions"]["delete_sqlite"]["enabled"])
        self.assertTrue(sqlite_actions["action_state"]["is_sqlite_source"])
        self.assertTrue(sqlite_actions["actions"]["delete_sqlite"]["requires_confirmation"])
        self.assertEqual(sqlite_actions["action_schema"]["schema_version"], "data_source_action_schema.v1")
        self.assertEqual(sqlite_actions["action_schema"]["actions"]["save_sqlite"]["engine_action"], "save_table")
        self.assertTrue(sqlite_actions["action_schema"]["actions"]["delete_sqlite"]["requires_confirmation"])
        self.assertEqual(
            sqlite_actions["action_schema"]["result_schemas"]["data_source_state"]["schema_version"],
            "data_source_state.v1",
        )
        self.assertTrue(service_desc["ok"])
        self.assertEqual(service_desc["schema_version"], "data_source_service.v1")
        self.assertEqual(service_desc["protocol_family"], "data_source_service")
        self.assertTrue(service_desc["capabilities"]["clipboard_parse"])
        self.assertTrue(service_desc["capabilities"]["panel_state"])
        self.assertEqual(
            service_desc["actions"]["build_data_source_panel_state"]["engine_action"],
            "build_data_source_panel_state",
        )
        self.assertEqual(service_desc["data_actions"]["patch_cell"]["engine_action"], "patch_table_cell")
        self.assertEqual(
            service_desc["actions"]["describe_data_source_actions"]["engine_action"],
            "describe_data_source_actions",
        )
        self.assertEqual(service_desc["table_actions"]["load_table"]["engine_action"], "load_table")
        self.assertEqual(
            service_desc["table_actions"]["create_table_handle"]["result"],
            "table_handle",
        )
        self.assertEqual(
            service_desc["table_actions"]["get_table_handle_page"]["engine_action"],
            "get_table_handle_page",
        )
        self.assertIn("table_actions", service_desc)
        self.assertIn("load_table", service_desc["action_schema"]["actions"])
        self.assertEqual(
            service_desc["action_schema"]["actions"]["release_table_handle"]["result"],
            "table_handle_release",
        )
        self.assertEqual([item["id"] for item in service_desc["save_modes"]["modes"]], ["replace", "timestamp", "fail", "append"])
        self.assertEqual(service_desc["result_schemas"]["data_source_state"]["schema_version"], "data_source_state.v1")
        self.assertEqual(service_desc["result_schemas"]["data_source_panel_state"]["schema_version"], "data_source_panel_state.v1")
        self.assertEqual(service_desc["result_schemas"]["table_handle"]["schema_version"], "table_handle.v1")
        self.assertTrue(panel["ok"])
        panel_state = panel["panel_state"]
        self.assertEqual(panel_state["schema_version"], "data_source_panel_state.v1")
        self.assertEqual(panel_state["view_state"]["status_text"], "demo：1 行 x 2 列，分页预览，未保存")
        self.assertEqual(panel_state["view_state"]["page"]["offset"], 10)
        self.assertEqual(panel_state["view_state"]["page_status_text"], "分页预览：第 11-11 行，每页 50，还有下一页")
        self.assertTrue(panel_state["view_state"]["page_controls"]["page_size_enabled"])
        self.assertTrue(panel_state["view_state"]["page_controls"]["prev_enabled"])
        self.assertTrue(panel_state["view_state"]["page_controls"]["next_enabled"])
        self.assertTrue(panel_state["view_state"]["page_controls"]["load_full_enabled"])
        self.assertEqual(panel_state["view_state"]["search"]["current_cell"], {"row": 0, "column": 1})
        self.assertTrue(panel_state["view_state"]["action_enabled"]["delete_sqlite"])
        self.assertIn("build_data_source_panel_state", panel_state["service"]["action_ids"])
        self.assertIn("create_table_handle", panel_state["service"]["table_action_ids"])
        self.assertEqual(panel_state["save_modes"]["mode_ids"], ["replace", "timestamp", "fail", "append"])
        self.assertEqual(normalize_table_headers(["", "A", "A"]), ["列1", "A", "A_2"])

    def test_table_search_navigation_is_ui_free(self):
        table = {
            "headers": ["A", "B"],
            "rows": [["alpha", "beta alpha"], ["none", "alpha"]],
        }

        matches = search_table(table, "alpha")
        flattened = flatten_search_matches(matches)
        first = build_search_navigation(matches, reset=True)
        second = build_search_navigation(matches, current_index=0, offset=1)
        wrapped = build_search_navigation(matches, current_index=0, offset=-1)
        service_result = TableDataService().search_table(table, "alpha", current_index=0, offset=1, reset=False)

        self.assertEqual(len(matches), 2)
        self.assertEqual([(item["row"], item["column"]) for item in flattened], [(0, 0), (0, 1), (1, 1)])
        self.assertEqual(first["status_text"], "1/3")
        self.assertEqual(first["highlighted_rows"], [0, 1])
        self.assertEqual(second["current_match"]["column"], 1)
        self.assertEqual(wrapped["current_match"]["row"], 1)
        self.assertEqual(service_result["count"], 2)
        self.assertEqual(service_result["cell_count"], 3)
        self.assertEqual(service_result["navigation"]["current_cell"], {"row": 0, "column": 1})

    def test_table_save_modes_are_described_and_normalized(self):
        service = TableDataService()

        described = service.describe_table_save_modes()
        normalized = service.normalize_table_save_mode("存在则报错")
        invalid = service.normalize_table_save_mode("局部覆盖")

        self.assertEqual(describe_save_modes()[0]["id"], "replace")
        self.assertEqual(normalize_save_mode("覆盖同名表"), "replace")
        self.assertEqual(normalize_save_mode("timestamp_new"), "timestamp")
        self.assertEqual(normalize_save_mode("追加"), "append")
        self.assertTrue(described["ok"])
        self.assertEqual(described["schema_version"], "table_save_modes.v1")
        self.assertEqual([item["id"] for item in described["modes"]], ["replace", "timestamp", "fail", "append"])
        self.assertEqual(described["mode_field"]["choices_source"], "modes")
        self.assertEqual(normalized["mode"], "fail")
        self.assertFalse(invalid["ok"])
        self.assertEqual(invalid["issues"][0]["code"], "invalid_save_mode")

    def test_service_saves_and_deletes_sqlite_table_with_confirmation(self):
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "data.db")
            service = TableDataService()
            table = {"headers": ["A"], "rows": [["x"]]}

            saved = service.save_table(table, db_path=db_path, table_name="input_data", mode="覆盖同名表")
            manager = TableAccessManager(db_path)
            saved_rows = manager.read_table("input_data")["rows"]
            blocked = service.delete_table(db_path=db_path, table_name="input_data", confirmed=False)
            deleted = service.delete_table(db_path=db_path, table_name="input_data", backup=True, confirmed=True)

            self.assertTrue(saved["ok"])
            self.assertEqual(saved["source"]["table_name"], "input_data")
            self.assertEqual(saved["mode"], "replace")
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
