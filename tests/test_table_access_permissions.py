# -*- coding: utf-8 -*-
import os
import sqlite3
import tempfile
import threading
import types
import unittest
from contextlib import contextmanager

from DataFlowKit import PlanWorkflowWindow, TableAccessManager
from plugins import word_excel_read_to_db_plugin_v1 as read_plugin
from shared.table_access_policy import extract_read_tables
from workflow.nodes.data_nodes import apply_numeric_column_node, apply_replace_node
from workflow import output_node_runtime


@contextmanager
def closing_sqlite_connection(path):
    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


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
        with closing_sqlite_connection(self.db_path) as conn:
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

    def test_replace_write_failure_rolls_back_original_table(self):
        manager = TableAccessManager(self.db_path)

        def fail_insert(_cur, _sql, _rows):
            raise RuntimeError("forced insert failure")

        manager._executemany = fail_insert
        with self.assertRaisesRegex(RuntimeError, "forced insert failure"):
            manager.write_table("allowed", ["a"], [["new"]], mode="replace")
        with closing_sqlite_connection(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT a FROM allowed").fetchall(), [("ok",)])

    def test_timestamp_write_failure_does_not_leave_empty_table(self):
        manager = TableAccessManager(self.db_path)
        before = set(manager.list_tables())

        def fail_insert(_cur, _sql, _rows):
            raise RuntimeError("forced insert failure")

        manager._executemany = fail_insert
        with self.assertRaisesRegex(RuntimeError, "forced insert failure"):
            manager.write_table("allowed", ["a"], [["new"]], mode="timestamp")
        self.assertEqual(set(manager.list_tables()), before)

    def test_append_write_failure_rolls_back_added_column(self):
        manager = TableAccessManager(self.db_path)

        def fail_insert(_cur, _sql, _rows):
            raise RuntimeError("forced insert failure")

        manager._executemany = fail_insert
        with self.assertRaisesRegex(RuntimeError, "forced insert failure"):
            manager.write_table("allowed", ["a", "b"], [["new", "value"]], mode="append")
        self.assertEqual(manager.get_columns("allowed"), ["a"])
        with closing_sqlite_connection(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT a FROM allowed").fetchall(), [("ok",)])

    def test_clear_and_writeback_failure_rolls_back_all_changes(self):
        with closing_sqlite_connection(self.db_path) as conn:
            conn.execute("INSERT INTO allowed VALUES ('old-2')")
            conn.commit()
        manager = TableAccessManager(self.db_path)
        original_execute = manager._execute_writeback_update
        update_count = {"value": 0}

        def fail_second_update(cur, sql, params):
            update_count["value"] += 1
            if update_count["value"] == 2:
                raise RuntimeError("forced second update failure")
            return original_execute(cur, sql, params)

        manager._execute_writeback_update = fail_second_update
        actions = [
            {"write": True, "target_field": "a", "target_rowid": 1, "new_value": "new-1"},
            {"write": True, "target_field": "a", "target_rowid": 2, "new_value": "new-2"},
        ]
        with self.assertRaisesRegex(RuntimeError, "forced second update failure"):
            manager.apply_writeback_transaction("allowed", actions, clear_fields=["a"])
        with closing_sqlite_connection(self.db_path) as conn:
            self.assertEqual(
                conn.execute("SELECT a FROM allowed ORDER BY rowid").fetchall(),
                [("ok",), ("old-2",)],
            )

    def test_clear_and_writeback_cancel_rolls_back_all_changes(self):
        manager = TableAccessManager(self.db_path)
        cancel_event = threading.Event()
        cancel_event.set()
        actions = [
            {"write": True, "target_field": "a", "target_rowid": 1, "new_value": "new"},
        ]
        with self.assertRaisesRegex(RuntimeError, "用户取消"):
            manager.apply_writeback_transaction(
                "allowed",
                actions,
                clear_fields=["a"],
                cancel_event=cancel_event,
            )
        with closing_sqlite_connection(self.db_path) as conn:
            self.assertEqual(conn.execute("SELECT a FROM allowed").fetchall(), [("ok",)])

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
        with closing_sqlite_connection(self.db_path) as conn:
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

    def test_replace_node_reports_invalid_fixed_regex(self):
        with self.assertRaisesRegex(ValueError, "批量替换正则错误"):
            apply_replace_node(
                ["text"],
                [["abc"]],
                {
                    "target_field": "text",
                    "match_mode": "正则匹配",
                    "replace_mode": "局部替换匹配字符串",
                    "match_value": "(",
                    "replace_value": "x",
                },
            )

    def test_replace_node_honors_cancel_signal(self):
        cancel_event = threading.Event()
        cancel_event.set()
        with self.assertRaisesRegex(RuntimeError, "用户取消"):
            apply_replace_node(
                ["text"],
                [["abc"]],
                {
                    "target_field": "text",
                    "match_mode": "包含",
                    "replace_mode": "局部替换匹配字符串",
                    "match_value": "a",
                    "replace_value": "x",
                },
                context={"check_cancelled": lambda index: (_ for _ in ()).throw(RuntimeError("用户取消"))},
            )

    def test_row_expansion_rejects_excessive_target(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        with self.assertRaisesRegex(ValueError, "超过安全上限"):
            window.ensure_row_count(
                [],
                window.MAX_EXPANDED_ROWS + 1,
                1,
            )

    def test_numeric_column_uses_decimal_for_long_integer(self):
        headers, rows, _stat = apply_numeric_column_node(
            ["n"],
            [["123456789012345678"]],
            {
                "target_field": "n",
                "output_mode": "生成新字段",
                "output_field": "result",
                "operation": "加",
                "operand_source": "固定值",
                "operand_value": "1",
                "decimal_places": "自动",
                "range_mode": "全部行",
            },
        )
        self.assertEqual(headers, ["n", "result"])
        self.assertEqual(rows, [["123456789012345678", "123456789012345679"]])

    def test_datetime_warning_marks_ambiguous_month_and_day(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        warning = window.get_datetime_parse_warning(
            "03/06/26",
            {
                "input_structure": "分隔符",
                "date_delimiter": "自动识别",
                "date_order": "月-日-年",
                "year_rule": "20xx",
            },
            {"year": 2026, "month": 3, "day": 6},
        )
        self.assertIn("确认月日顺序", warning)

    def filter_window(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        window.get_workflow_db_path = lambda context=None: self.db_path
        window.get_workflow_sqlite_columns = (
            lambda table_name, context=None: TableAccessManager(self.db_path).get_columns(table_name)
        )
        window.get_table_manager = (
            lambda *args, **kwargs: TableAccessManager(self.db_path)
        )
        return window

    def test_filter_current_field_prefix_does_not_leak_to_output_header(self):
        window = self.filter_window()
        headers, rows, _stat = window.apply_filter_node(
            ["编码"],
            [["A001"]],
            {"conditions": [], "join_rules": [], "extra_tables": [], "output_fields": ["当前表.编码"]},
        )
        self.assertEqual(headers, ["编码"])
        self.assertEqual(rows, [["A001"]])

    def test_two_consecutive_filters_do_not_accumulate_current_table_prefix(self):
        window = self.filter_window()
        headers, rows, _stat = window.apply_filter_node(
            ["编码"],
            [["A001"]],
            {"conditions": [], "join_rules": [], "extra_tables": [], "output_fields": ["当前表.编码"]},
        )
        second_lookup_fields = window.get_plan_filter_available_fields(headers, [], {})
        headers, rows, _stat = window.apply_filter_node(
            headers,
            rows,
            {
                "conditions": [],
                "join_rules": [],
                "extra_tables": [],
                "output_fields": second_lookup_fields,
            },
        )
        self.assertEqual(headers, ["编码"])
        self.assertEqual(rows, [["A001"]])

    def test_three_consecutive_filters_keep_same_header(self):
        window = self.filter_window()
        headers = ["编码"]
        rows = [["A001"]]
        for _index in range(3):
            lookup_fields = window.get_plan_filter_available_fields(headers, [], {})
            headers, rows, _stat = window.apply_filter_node(
                headers,
                rows,
                {
                    "conditions": [],
                    "join_rules": [],
                    "extra_tables": [],
                    "output_fields": lookup_fields,
                },
            )
        self.assertEqual(headers, ["编码"])
        self.assertEqual(rows, [["A001"]])

    def test_run_plan_three_filters_keep_same_header(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        window.nodes = []
        window.plugin_registry = {}
        filter_config = {
            "conditions": [],
            "join_rules": [],
            "extra_tables": [],
            "output_fields": ["当前表.编码"],
        }
        snapshot = {
            "nodes": [
                {
                    "type": "高级筛选",
                    "name": f"筛选{index}",
                    "enabled": True,
                    "config": dict(filter_config),
                }
                for index in range(1, 4)
            ],
            "headers": ["编码"],
            "rows": [["A001"]],
            "db_path": "",
            "table_access_policy": "audit",
        }
        headers, rows, _logs = window.run_plan(
            raise_error=True,
            workflow_snapshot=snapshot,
        )
        self.assertEqual(headers, ["编码"])
        self.assertEqual(rows, [["A001"]])

    def test_filter_runtime_migrates_old_nested_current_field_references(self):
        window = self.filter_window()
        config = {
            "conditions": [{
                "field": "当前表.当前表.编码",
                "op": "等于",
                "value_source": "固定值",
                "value": "A001",
            }],
            "join_rules": [],
            "extra_tables": [],
            "output_fields": ["当前表.当前表.编码"],
        }
        headers, rows, _stat = window.apply_filter_node(
            ["编码"],
            [["A001"], ["B002"]],
            config,
        )
        self.assertEqual(headers, ["编码"])
        self.assertEqual(rows, [["A001"]])
        self.assertEqual(config["conditions"][0]["field"], "当前表.当前表.编码")
        self.assertEqual(config["conditions"][0]["value"], "A001")

    def test_filter_config_migration_updates_field_value_and_join_refs_only(self):
        window = self.filter_window()
        config = {
            "conditions": [
                {
                    "field": "当前表.当前表.编码",
                    "op": "等于",
                    "value_source": "字段值",
                    "value": "当前表.当前表.对照编码",
                },
                {
                    "field": "当前表.当前表.编码",
                    "op": "等于",
                    "value_source": "固定值",
                    "value": "当前表.当前表.这是普通文本",
                },
            ],
            "join_rules": [{
                "left": "当前表.当前表.编码",
                "op": "等于",
                "right": "allowed.a",
            }],
            "extra_tables": ["allowed"],
            "output_fields": ["当前表.当前表.编码", "allowed.a"],
        }
        window.normalize_plan_filter_config_field_references(
            config,
            ["编码", "对照编码"],
            ["allowed"],
        )
        self.assertEqual(config["conditions"][0]["field"], "当前表.编码")
        self.assertEqual(config["conditions"][0]["value"], "当前表.对照编码")
        self.assertEqual(config["conditions"][1]["value"], "当前表.当前表.这是普通文本")
        self.assertEqual(config["join_rules"][0]["left"], "当前表.编码")
        self.assertEqual(config["join_rules"][0]["right"], "allowed.a")
        self.assertEqual(config["output_fields"], ["当前表.编码", "allowed.a"])

    def test_filter_preserves_real_header_that_starts_with_current_table_prefix(self):
        window = self.filter_window()
        headers, rows, _stat = window.apply_filter_node(
            ["当前表.编码"],
            [["A001"]],
            {
                "conditions": [],
                "join_rules": [],
                "extra_tables": [],
                "output_fields": ["当前表.当前表.编码"],
            },
        )
        self.assertEqual(headers, ["当前表.编码"])
        self.assertEqual(rows, [["A001"]])

    def test_filter_output_headers_use_stable_suffix_for_name_collision(self):
        window = self.filter_window()
        lookup_fields = ["当前表.物料表.名称", "物料表.名称", "物料表.名称"]
        output_headers = window.get_plan_filter_output_headers(
            lookup_fields,
            ["物料表.名称"],
        )
        self.assertEqual(output_headers, ["物料表.名称", "物料表.名称_2", "物料表.名称_3"])
        self.assertEqual(
            window.get_plan_filter_output_header_conflicts(
                lookup_fields,
                ["物料表.名称"],
            ),
            ["物料表.名称"],
        )

    def test_filter_multi_table_keeps_external_qualified_name_only(self):
        window = self.filter_window()
        headers, rows, _stat = window.apply_filter_node(
            ["编码"],
            [["ok"]],
            {
                "conditions": [],
                "join_rules": [{
                    "left": "当前表.编码",
                    "op": "等于",
                    "right": "allowed.a",
                }],
                "extra_tables": ["allowed"],
                "output_fields": ["当前表.编码", "allowed.a"],
            },
        )
        self.assertEqual(headers, ["编码", "allowed.a"])
        self.assertEqual(rows, [["ok", "ok"]])

    def test_filter_config_probe_returns_downstream_headers_without_current_prefix(self):
        window = self.filter_window()
        headers, rows, stat = window.apply_filter_node(
            ["编码"],
            [["ok"]],
            {
                "conditions": [],
                "join_rules": [],
                "extra_tables": ["allowed"],
                "output_fields": [],
            },
            context={"is_config_probe": True},
        )
        self.assertEqual(headers, ["编码", "allowed.a"])
        self.assertEqual(rows, [])
        self.assertIn("配置探测", stat)

    def test_group_filter_analysis_covers_conditions_joins_and_outputs(self):
        window = self.filter_window()
        info = window.analyze_group_inner_node_field_io({
            "type": "高级筛选",
            "config": {
                "conditions": [
                    {
                        "field": "当前表.编码",
                        "value_source": "字段值",
                        "value": "当前表.对照编码",
                    },
                    {
                        "field": "allowed.a",
                        "value_source": "固定值",
                        "value": "ok",
                    },
                ],
                "join_rules": [{
                    "left": "当前表.编码",
                    "right": "allowed.a",
                }],
                "extra_tables": ["allowed"],
                "output_fields": ["当前表.编码", "allowed.a"],
            },
        })
        self.assertEqual(info["read_fields"], ["编码", "对照编码"])
        self.assertEqual(info["write_fields"], ["编码", "allowed.a"])

    def test_group_filter_does_not_require_field_created_by_previous_node(self):
        window = self.filter_window()
        inferred, details = window.infer_group_input_fields_from_nodes([
            {
                "type": "新建列",
                "enabled": True,
                "config": {"columns_text": "编码"},
            },
            {
                "type": "高级筛选",
                "enabled": True,
                "config": {
                    "conditions": [{"field": "当前表.编码", "value": "A001"}],
                    "join_rules": [],
                    "extra_tables": [],
                    "output_fields": ["当前表.编码"],
                },
            },
        ])
        self.assertEqual(inferred, [])
        self.assertEqual(details[1]["reads"], ["编码"])
        self.assertEqual(details[1]["writes"], ["编码"])

    def test_group_filter_external_output_is_available_to_later_node(self):
        window = self.filter_window()
        inferred, details = window.infer_group_input_fields_from_nodes([
            {
                "type": "高级筛选",
                "enabled": True,
                "config": {
                    "conditions": [],
                    "join_rules": [{
                        "left": "当前表.编码",
                        "right": "allowed.a",
                    }],
                    "extra_tables": ["allowed"],
                    "output_fields": ["当前表.编码", "allowed.a"],
                },
            },
            {
                "type": "合并列",
                "enabled": True,
                "config": {
                    "fields": ["allowed.a"],
                    "output_field": "组合结果",
                },
            },
        ])
        self.assertEqual(inferred, ["编码"])
        self.assertEqual(details[0]["writes"], ["编码", "allowed.a"])
        self.assertEqual(details[1]["required"], [])

    def test_group_filter_reports_only_missing_current_fields(self):
        window = self.filter_window()
        inferred, _details = window.infer_group_input_fields_from_nodes([{
            "type": "高级筛选",
            "enabled": True,
            "config": {
                "conditions": [{
                    "field": "当前表.编码",
                    "value_source": "字段值",
                    "value": "当前表.对照编码",
                }],
                "join_rules": [{
                    "left": "当前表.编码",
                    "right": "allowed.a",
                }],
                "extra_tables": ["allowed"],
                "output_fields": ["allowed.a"],
            },
        }])
        self.assertEqual(inferred, ["编码", "对照编码"])

    def test_group_filter_without_explicit_output_resolves_sqlite_side_fields(self):
        window = self.filter_window()
        inferred, details = window.infer_group_input_fields_from_nodes([
            {
                "type": "高级筛选",
                "enabled": True,
                "config": {
                    "conditions": [],
                    "join_rules": [{
                        "left": "当前表.编码",
                        "right": "allowed.a",
                    }],
                    "extra_tables": ["allowed"],
                    "output_fields": [],
                },
            },
            {
                "type": "合并列",
                "enabled": True,
                "config": {
                    "fields": ["allowed.a"],
                    "output_field": "组合结果",
                },
            },
        ], context={})
        self.assertEqual(inferred, ["编码"])
        self.assertEqual(details[0]["writes"], ["allowed.a"])
        self.assertEqual(details[0]["write_prefixes"], ["allowed."])
        self.assertEqual(details[1]["required"], [])

    def test_group_filter_without_explicit_output_resolves_transit_side_fields(self):
        window = self.filter_window()
        context = {
            "transit_tables": {
                "副表": {
                    "headers": ["名称", "规格"],
                    "rows": [],
                },
            },
        }
        inferred, details = window.infer_group_input_fields_from_nodes([
            {
                "type": "高级筛选",
                "enabled": True,
                "config": {
                    "conditions": [],
                    "join_rules": [],
                    "extra_tables": ["中转:副表"],
                    "output_fields": [],
                },
            },
            {
                "type": "合并列",
                "enabled": True,
                "config": {
                    "fields": ["中转:副表.规格"],
                    "output_field": "组合结果",
                },
            },
        ], context=context)
        self.assertEqual(inferred, [])
        self.assertEqual(
            details[0]["writes"],
            ["中转:副表.名称", "中转:副表.规格"],
        )
        self.assertEqual(details[1]["required"], [])

    def test_group_filter_without_explicit_output_uses_prefix_when_schema_unavailable(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)

        def unavailable_schema(*_args, **_kwargs):
            raise ValueError("数据库不可用")

        window.get_workflow_sqlite_columns = unavailable_schema
        inferred, details = window.infer_group_input_fields_from_nodes([
            {
                "type": "高级筛选",
                "enabled": True,
                "config": {
                    "conditions": [],
                    "join_rules": [],
                    "extra_tables": ["missing"],
                    "output_fields": [],
                },
            },
            {
                "type": "合并列",
                "enabled": True,
                "config": {
                    "fields": ["missing.any"],
                    "output_field": "组合结果",
                },
            },
        ], context={})
        self.assertEqual(inferred, [])
        self.assertEqual(details[0]["writes"], [])
        self.assertEqual(details[0]["write_prefixes"], ["missing."])
        self.assertIn("结构未解析", details[0]["note"])
        self.assertEqual(details[1]["required"], [])

    def test_group_filter_explicit_output_does_not_enable_side_table_prefix(self):
        window = self.filter_window()
        inferred, details = window.infer_group_input_fields_from_nodes([
            {
                "type": "高级筛选",
                "enabled": True,
                "config": {
                    "conditions": [],
                    "join_rules": [],
                    "extra_tables": ["allowed"],
                    "output_fields": ["allowed.a"],
                },
            },
            {
                "type": "合并列",
                "enabled": True,
                "config": {
                    "fields": ["allowed.other"],
                    "output_field": "组合结果",
                },
            },
        ], context={})
        self.assertEqual(inferred, ["allowed.other"])
        self.assertEqual(details[0]["writes"], ["allowed.a"])
        self.assertEqual(details[0]["write_prefixes"], [])
        self.assertEqual(details[1]["required"], ["allowed.other"])

    def test_group_filter_old_nested_reference_removes_one_context_prefix(self):
        window = self.filter_window()
        info = window.analyze_group_inner_node_field_io({
            "type": "高级筛选",
            "config": {
                "conditions": [{"field": "当前表.当前表.编码"}],
                "join_rules": [],
                "extra_tables": [],
                "output_fields": ["当前表.当前表.编码"],
            },
        })
        self.assertEqual(info["read_fields"], ["当前表.编码"])
        self.assertEqual(info["write_fields"], ["当前表.编码"])

    def test_save_transit_checks_permission_before_memory_write(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)

        def deny_write(*_args, **_kwargs):
            raise PermissionError("blocked transit write")

        window.check_transit_table_write_permission = deny_write
        window.log_transit_table_event = lambda *args, **kwargs: None
        context = {"transit_tables": {}}

        with self.assertRaisesRegex(PermissionError, "blocked transit write"):
            window.apply_save_transit_node(
                ["A"],
                [["x"]],
                {"transit_name": "副表", "save_memory": True},
                context=context,
            )

        self.assertEqual(context["transit_tables"], {})

    def test_save_transit_writes_memory_after_permission_and_logs(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        events = []
        window.check_transit_table_write_permission = lambda *args, **kwargs: "manager"
        window.log_transit_table_event = lambda *args, **kwargs: events.append((args, kwargs))
        context = {"transit_tables": {"副表": {"headers": ["A"], "rows": [["old"]]}}}

        headers, rows, message = window.apply_save_transit_node(
            ["B"],
            [["new"]],
            {"transit_name": "副表", "save_memory": True, "append_memory": True},
            context=context,
        )

        self.assertEqual(headers, ["B"])
        self.assertEqual(rows, [["new"]])
        self.assertEqual(context["transit_tables"]["副表"], {
            "headers": ["A", "B"],
            "rows": [["old", ""], ["", "new"]],
            "source": "保存中转数据:追加",
        })
        self.assertIn("内存副表追加：副表", message)
        self.assertEqual(events[0][0][1], "append_transit_table")
        self.assertEqual(events[0][1]["appended_rows"], 1)

    def test_selected_columns_write_transit_helper_checks_permission_before_write(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        window.apply_selected_columns_to_memory_table = lambda *args, **kwargs: (["B"], [["new"]])

        def deny_write(*_args, **_kwargs):
            raise PermissionError("blocked selected columns transit write")

        window.check_transit_table_write_permission = deny_write
        window.log_transit_table_event = lambda *args, **kwargs: None
        context = {"transit_tables": {}}

        with self.assertRaisesRegex(PermissionError, "blocked selected columns transit write"):
            window.apply_selected_columns_write_transit_table(
                ["A"],
                [["old"]],
                {"write_mode": "局部覆盖，保留目标原行数"},
                context,
                "目标副表",
                ["B"],
                [["new"]],
            )

        self.assertEqual(context["transit_tables"], {})

    def test_selected_columns_write_sqlite_helper_uses_rebuild_and_merge_modes(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        window.app = types.SimpleNamespace(sanitize_sql_name=lambda name, default: name or default)
        calls = []
        window.save_result_to_sqlite = lambda headers, rows, table, **kwargs: calls.append((headers, rows, table, kwargs)) or table

        headers, rows, message = window.apply_selected_columns_write_sqlite_table(
            ["A"],
            [["old"]],
            {"write_mode": "覆盖重建目标表", "backup_before_write": False},
            {"transit_tables": {}},
            "目标表",
            ["B"],
            [["new"]],
        )

        self.assertEqual((headers, rows), (["A"], [["old"]]))
        self.assertIn("已覆盖重建 SQLite 表：目标表", message)
        self.assertEqual(calls[0][0], ["B"])
        self.assertEqual(calls[0][1], [["new"]])
        self.assertFalse(calls[0][3]["backup"])

        window.get_workflow_db_path = lambda context=None: __file__
        manager = types.SimpleNamespace(
            table_exists=lambda table: True,
            read_table=lambda table: {"headers": ["ID"], "rows": [["1"]]},
        )
        window.get_table_manager = lambda context=None, node_type=None: manager
        calls.clear()
        _headers, _rows, message = window.apply_selected_columns_write_sqlite_table(
            ["A"],
            [["old"]],
            {"write_mode": "局部覆盖，保留目标原行数"},
            {"transit_tables": {}},
            "目标表",
            ["B"],
            [["new"]],
        )

        self.assertIn("已复制选定列到 SQLite 表字段：目标表", message)
        self.assertEqual(calls[0][0], ["ID", "B"])
        self.assertEqual(calls[0][1], [["1", "new"]])

    def test_output_runtime_sqlite_helper_does_not_depend_on_window_selected_columns_wrappers(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        window.app = types.SimpleNamespace(sanitize_sql_name=lambda name, default: name or default)
        window.get_workflow_db_path = lambda context=None: __file__
        manager = types.SimpleNamespace(
            table_exists=lambda table: True,
            read_table=lambda table: {"headers": ["ID"], "rows": [["1"]]},
        )
        window.get_table_manager = lambda context=None, node_type=None: manager
        calls = []
        window.save_result_to_sqlite = lambda headers, rows, table, **kwargs: calls.append((headers, rows, table, kwargs)) or table

        def legacy_wrapper_should_not_be_called(*_args, **_kwargs):
            raise AssertionError("output runtime should call workflow helpers directly")

        window.read_selected_columns_target_table = legacy_wrapper_should_not_be_called
        window.apply_selected_columns_to_memory_table = legacy_wrapper_should_not_be_called

        _headers, _rows, message = output_node_runtime.apply_selected_columns_write_sqlite_table(
            window,
            ["A"],
            [["old"]],
            {"write_mode": "局部覆盖，保留目标原行数"},
            {"transit_tables": {}},
            "目标表",
            ["B"],
            [["new"]],
        )

        self.assertIn("已复制选定列到 SQLite 表字段：目标表", message)
        self.assertEqual(calls[0][0], ["ID", "B"])
        self.assertEqual(calls[0][1], [["1", "new"]])


if __name__ == "__main__":
    unittest.main()
