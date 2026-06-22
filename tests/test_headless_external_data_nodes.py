# -*- coding: utf-8 -*-
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine.headless import HeadlessWorkflowEngine
from engine.workflow_services import WorkflowServices


class HeadlessExternalDataNodesTests(unittest.TestCase):
    def test_match_value_output_uses_context_table_source(self):
        engine = HeadlessWorkflowEngine()
        plan = {
            "nodes": [{
                "node_type_id": "core.match_value_output",
                "config": {
                    "source_field": "Source",
                    "lookup_table": "lookup",
                    "lookup_fields": ["ColA", "ColB"],
                    "match_mode": "完全相等",
                    "multi_match_policy": "合并所有字段名",
                    "multi_match_separator": "|",
                },
            }],
            "headers": ["Source"],
            "rows": [["beta"], ["alpha"], ["none"]],
        }

        result = engine.preview_plan(
            plan,
            initial_context={
                "table_sources": {
                    "lookup": {
                        "type": "inline",
                        "headers": ["ColA", "ColB"],
                        "rows": [["alpha", "beta"], ["gamma", "alpha"]],
                    }
                }
            },
        )

        self.assertEqual(result.headers, ["Source", "匹配字段名", "匹配值", "匹配行号", "匹配状态"])
        self.assertEqual(result.rows[0], ["beta", "ColB", "beta", "1", "成功"])
        self.assertEqual(result.rows[1], ["alpha", "ColA|ColB", "alpha", "1|2", "多匹配，共2项"])
        self.assertEqual(result.rows[2], ["none", "未匹配", "", "", "未匹配"])
        self.assertIn("匹配值输出列名完成", result.logs[0])

    def test_filter_node_uses_context_table_source(self):
        engine = HeadlessWorkflowEngine()
        plan = {
            "nodes": [{
                "node_type_id": "core.filter",
                "config": {
                    "extra_tables": ["lookup"],
                    "join_rules": [{"left": "当前表.Code", "op": "等于", "right": "lookup.Code"}],
                    "output_fields": ["当前表.Code", "lookup.Name"],
                    "result_limit": "100",
                },
            }],
            "headers": ["Code"],
            "rows": [["A"], ["B"]],
        }

        result = engine.preview_plan(
            plan,
            initial_context={
                "table_sources": {
                    "lookup": {
                        "type": "inline",
                        "headers": ["Code", "Name"],
                        "rows": [["A", "Alpha"], ["C", "Gamma"]],
                    }
                }
            },
        )

        self.assertEqual(result.headers, ["Code", "lookup.Name"])
        self.assertEqual(result.rows, [["A", "Alpha"]])
        self.assertIn("筛选/匹配后 1 行", result.logs[0])

    def test_selected_columns_preview_does_not_write_sqlite(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            db_path = str(Path(temp_dir) / "preview.db")
            engine = HeadlessWorkflowEngine(services=WorkflowServices(db_path=db_path))
            plan = {
                "nodes": [{
                    "node_type_id": "core.selected_columns_write",
                    "config": {
                        "enable_write": True,
                        "target_type": "SQLite表",
                        "target_table": "selected_out",
                        "selected_fields": ["B"],
                    },
                }],
                "headers": ["A", "B"],
                "rows": [["a", "b"]],
            }

            result = engine.preview_plan(plan)

        self.assertEqual(result.headers, ["A", "B"])
        self.assertEqual(result.rows, [["a", "b"]])
        self.assertFalse(os.path.exists(db_path))
        self.assertIn("预览计划", result.logs[0])

    def test_selected_columns_execute_writes_current_and_transit_targets(self):
        engine = HeadlessWorkflowEngine()
        current_plan = {
            "nodes": [{
                "node_type_id": "core.selected_columns_write",
                "config": {
                    "enable_write": True,
                    "target_type": "当前工作表",
                    "selected_fields": ["B"],
                    "field_name_mode": "添加后缀",
                    "target_suffix": "_copy",
                    "overwrite_rule": "覆盖全部",
                },
            }],
            "headers": ["A", "B"],
            "rows": [["a", "b"]],
        }

        current_result = engine.run_plan(current_plan, execute_actions=True)

        self.assertEqual(current_result.headers, ["A", "B", "B_copy"])
        self.assertEqual(current_result.rows, [["a", "b", "b"]])

        transit_plan = {
            "nodes": [{
                "node_type_id": "core.selected_columns_write",
                "config": {
                    "enable_write": True,
                    "target_type": "中转副表",
                    "target_transit_table": "out",
                    "selected_fields": ["B"],
                    "overwrite_rule": "覆盖全部",
                },
            }],
            "headers": ["A", "B"],
            "rows": [["a", "b"]],
        }

        transit_result = engine.run_plan(transit_plan, execute_actions=True)

        self.assertEqual(transit_result.rows, [["a", "b"]])
        self.assertEqual(transit_result.context["transit_tables"]["out"]["headers"], ["B"])
        self.assertEqual(transit_result.context["transit_tables"]["out"]["rows"], [["b"]])

    def test_selected_columns_execute_writes_sqlite_through_services(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            db_path = str(Path(temp_dir) / "run.db")
            engine = HeadlessWorkflowEngine(services=WorkflowServices(db_path=db_path))
            plan = {
                "nodes": [{
                    "node_type_id": "core.selected_columns_write",
                    "config": {
                        "enable_write": True,
                        "target_type": "SQLite表",
                        "target_table": "selected_out",
                        "selected_fields": ["B"],
                        "field_name_mode": "添加前缀",
                        "target_prefix": "copied_",
                        "write_mode": "覆盖重建目标表",
                    },
                }],
                "headers": ["A", "B"],
                "rows": [["a", "b"]],
            }

            result = engine.run_plan(plan, execute_actions=True)
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute('SELECT copied_B FROM "selected_out"').fetchall()
            finally:
                conn.close()

        self.assertEqual(rows, [("b",)])
        self.assertIn("已覆盖重建 SQLite 表：selected_out", result.logs[0])


if __name__ == "__main__":
    unittest.main()
