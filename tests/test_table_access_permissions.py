# -*- coding: utf-8 -*-
import os
import sqlite3
import tempfile
import types
import unittest

from DataFlowKit import PlanWorkflowWindow, TableAccessManager
from plugins import word_excel_read_to_db_plugin_v1 as read_plugin
from shared.table_access_policy import extract_read_tables


def permission_set(**enabled):
    keys = [
        "read_table",
        "write_table",
        "create_table",
        "append_rows",
        "update_rows",
        "clear_table",
        "replace_table",
        "alter_schema",
        "delete_rows",
        "drop_table",
    ]
    return {key: bool(enabled.get(key)) for key in keys}


def access_entry(table="", table_pattern="", permissions=None, **extra):
    entry = {
        "role": "test",
        "table": table,
        "table_pattern": table_pattern,
        "pattern_type": "glob",
        "source_type": "SQLite表",
        "permissions": permissions or permission_set(),
        "field_mapping": {},
    }
    entry.update(extra)
    return entry


class TableAccessPermissionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.db_path = os.path.join(self.temp_dir.name, "permissions.db")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE allowed (a TEXT)")
            conn.execute("INSERT INTO allowed VALUES ('ok')")
            conn.execute("CREATE TABLE secret (a TEXT)")
            conn.execute("INSERT INTO secret VALUES ('hidden')")

    def tearDown(self):
        self.temp_dir.cleanup()

    def manager(self, entries, policy="strict"):
        return TableAccessManager(
            self.db_path,
            table_access={"version": 1, "tables": entries},
            permission_policy=policy,
        )

    def test_strict_mode_blocks_missing_table_role(self):
        manager = self.manager([])
        with self.assertRaises(PermissionError):
            manager.read_table("allowed")

    def test_log_only_role_records_but_does_not_block(self):
        entry = access_entry(
            table="allowed",
            permissions=permission_set(),
            log_only=True,
        )
        manager = self.manager([entry])
        self.assertTrue(manager.check_table_permission("allowed", ["read_table"], operation="test"))
        self.assertEqual(manager.events[-1]["status"], "warning")
        self.assertTrue(manager.events[-1]["log_only"])

    def test_execute_select_checks_each_referenced_table(self):
        entry = access_entry(
            table="allowed",
            permissions=permission_set(read_table=True),
        )
        manager = self.manager([entry])
        self.assertEqual(manager.execute_select("SELECT * FROM allowed")["rows"], [["ok"]])
        with self.assertRaises(PermissionError):
            manager.execute_select("SELECT * FROM secret")

    def test_execute_select_handles_cte_without_treating_alias_as_table(self):
        entry = access_entry(
            table="allowed",
            permissions=permission_set(read_table=True),
        )
        manager = self.manager([entry])
        data = manager.execute_select("WITH picked AS (SELECT * FROM allowed) SELECT * FROM picked")
        self.assertEqual(data["rows"], [["ok"]])
        self.assertEqual(extract_read_tables("WITH picked AS (SELECT * FROM allowed) SELECT * FROM picked"), ["allowed"])

    def test_execute_select_authorizer_blocks_complex_unauthorized_reads(self):
        entry = access_entry(
            table="allowed",
            permissions=permission_set(read_table=True),
        )
        manager = self.manager([entry])
        with self.assertRaises(PermissionError):
            manager.execute_select('SELECT allowed.a FROM allowed, "main"."secret"')

    def test_append_new_column_requires_alter_schema_and_create_field(self):
        denied_entry = access_entry(
            table="allowed",
            permissions=permission_set(write_table=True, append_rows=True, alter_schema=True),
            field_mapping={
                "a": {"target_field": "a", "permissions": {"write_field": True, "create_field": False}},
                "b": {"target_field": "b", "permissions": {"write_field": True, "create_field": False}},
            },
        )
        with self.assertRaises(PermissionError):
            self.manager([denied_entry]).write_table("allowed", ["a", "b"], [["x", "y"]], mode="append")

        allowed_entry = access_entry(
            table="allowed",
            permissions=permission_set(write_table=True, append_rows=True, alter_schema=True),
            field_mapping={
                "a": {"target_field": "a", "permissions": {"write_field": True, "create_field": False}},
                "b": {"target_field": "b", "permissions": {"write_field": True, "create_field": True}},
            },
        )
        manager = self.manager([allowed_entry])
        manager.write_table("allowed", ["a", "b"], [["x", "y"]], mode="append")
        self.assertEqual(manager.get_columns("allowed"), ["a", "b"])

    def test_dynamic_table_pattern_limits_plugin_output_scope(self):
        entry = access_entry(
            table_pattern="src_*",
            permissions=permission_set(write_table=True, create_table=True, replace_table=True),
        )
        manager = self.manager([entry])
        manager.write_table("src_demo", ["a"], [["1"]], mode="replace")
        with self.assertRaises(PermissionError):
            manager.write_table("other_demo", ["a"], [["1"]], mode="replace")

    def test_risk_advisory_is_not_strict_blocker(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        issues = [
            {"severity": "warning", "category": "risk", "blocking": False},
            {"severity": "warning", "category": "permission", "blocking": True},
        ]
        self.assertEqual(window.table_access_precheck_blocking(issues), [issues[1]])

    def test_word_reader_declares_dynamic_output_access(self):
        specs = read_plugin.get_table_access_spec({
            "table_prefix": "src_",
            "write_mode": "replace",
        })
        self.assertEqual(specs[0]["table_pattern"], "src_*")
        self.assertTrue(specs[0]["permissions"]["replace_table"])

    def test_plugin_node_default_access_includes_declared_scope(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        window.plugin_registry = {
            read_plugin.PLUGIN_INFO["id"]: {
                "module": read_plugin,
                "info": read_plugin.PLUGIN_INFO,
            }
        }
        node = {
            "type": "插件节点",
            "config": {
                "plugin_id": read_plugin.PLUGIN_INFO["id"],
                "params": {"table_prefix": "src_", "write_mode": "replace"},
                "input_tables": [],
            },
        }
        access = window.default_table_access_for_node(node)
        declared = [item for item in access["tables"] if item.get("declared_by") == read_plugin.PLUGIN_INFO["id"]]
        self.assertEqual(declared[0]["table_pattern"], "src_*")

    def precheck_window(self, nodes, registry):
        class DummyVar:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        window.nodes = nodes
        window.plugin_registry = registry
        window.current_transit_tables = {}
        window.output_mode_var = DummyVar("输出到主界面预览区")
        window.get_workflow_db_path = lambda: self.db_path
        return window

    def test_db_write_plugin_without_access_spec_is_precheck_warning(self):
        plugin_id = "missing_access_spec"
        module = types.SimpleNamespace()
        node = {
            "type": "插件节点",
            "enabled": True,
            "config": {"plugin_id": plugin_id, "params": {}, "input_tables": []},
        }
        window = self.precheck_window(
            [node],
            {plugin_id: {"module": module, "info": {"id": plugin_id, "danger_level": "db_write"}}},
        )
        issues = window.build_table_access_precheck(execute_actions=False)
        self.assertTrue(any("未声明表权限规格" in item.get("message", "") for item in issues))

    def test_plugin_dynamic_write_scope_star_is_risk_advisory(self):
        node = {
            "type": "插件节点",
            "enabled": True,
            "config": {
                "plugin_id": read_plugin.PLUGIN_INFO["id"],
                "params": {"table_prefix": "", "write_mode": "replace"},
                "input_tables": [],
            },
        }
        window = self.precheck_window(
            [node],
            {read_plugin.PLUGIN_INFO["id"]: {"module": read_plugin, "info": read_plugin.PLUGIN_INFO}},
        )
        issues = window.build_table_access_precheck(execute_actions=False)
        self.assertTrue(any("动态写表范围过宽" in item.get("message", "") for item in issues))

    def test_external_database_request_runs_through_manager(self):
        entry = access_entry(
            table_pattern="src_*",
            permissions=permission_set(write_table=True, create_table=True, replace_table=True),
        )
        manager = self.manager([entry])
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        window.get_table_manager = lambda *args, **kwargs: manager
        result = {
            "ok": True,
            "logs": [],
            "database_requests": [{
                "operation": "write_table",
                "table_name": "src_external",
                "headers": ["a"],
                "rows": [["managed"]],
                "mode": "replace",
            }],
        }
        context = {}
        rows = window.execute_external_plugin_database_requests(
            result,
            {"name": "test plugin"},
            context,
            execute_actions=True,
        )
        self.assertEqual(rows[0]["status"], "ok")
        with sqlite3.connect(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT a FROM src_external").fetchall(), [("managed",)])
        self.assertTrue(context["needs_refresh_table_list"])

    def test_workflow_output_manager_has_explicit_system_scope(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        window.get_workflow_db_path = lambda context=None: self.db_path
        context = {"table_access_policy": "strict", "table_access_logs": []}
        manager = window.get_workflow_output_manager("final_output", overwrite=False, context=context)
        manager.write_table("final_output", ["a"], [["done"]], mode="timestamp")
        self.assertEqual(manager.table_access.get("system_scope"), "workflow_output")
        self.assertTrue(context["table_access_logs"])

    def test_run_plan_audits_current_table_in_strict_mode(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        window.nodes = []
        window.plugin_registry = {}
        node = {
            "type": "新建列",
            "name": "add field",
            "enabled": True,
            "config": {
                "columns_text": "b",
                "value_mode": "统一默认值",
                "default_value": "v",
                "conflict_mode": "自动改名",
                "strip_column_name": True,
                "allow_empty_name": False,
            },
        }
        snapshot = {
            "nodes": [node],
            "headers": ["a"],
            "rows": [["x"]],
            "db_path": "",
            "table_access_policy": "strict",
        }
        headers, rows, logs, context = window.run_plan(
            raise_error=True,
            return_context=True,
            workflow_snapshot=snapshot,
        )
        self.assertEqual(headers, ["a", "b"])
        self.assertEqual(rows, [["x", "v"]])
        operations = [event.get("operation") for event in context.get("table_access_logs", [])]
        self.assertIn("permission_check", operations)
        self.assertIn("transform_current_table", operations)


if __name__ == "__main__":
    unittest.main()
