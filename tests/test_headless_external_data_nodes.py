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

    def test_writeback_preview_does_not_modify_sqlite(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            db_path = str(Path(temp_dir) / "preview_writeback.db")
            conn = sqlite3.connect(db_path)
            try:
                conn.execute('CREATE TABLE target (id TEXT, value TEXT)')
                conn.execute('INSERT INTO target (id, value) VALUES (?, ?)', ("A", "old"))
                conn.commit()
            finally:
                conn.close()

            engine = HeadlessWorkflowEngine(services=WorkflowServices(db_path=db_path))
            plan = {
                "nodes": [{
                    "node_type_id": "core.writeback",
                    "config": {
                        "enable_write": True,
                        "target_table": "target",
                        "use_match_rules": True,
                        "match_rules": [{"source_field": "id", "target_field": "id", "operator": "等于"}],
                        "field_mappings": [{"source_field": "value", "target_field": "value"}],
                    },
                }],
                "headers": ["id", "value"],
                "rows": [["A", "new"]],
            }

            result = engine.preview_plan(plan)
            conn = sqlite3.connect(db_path)
            try:
                value = conn.execute('SELECT value FROM target WHERE id=?', ("A",)).fetchone()[0]
            finally:
                conn.close()

        self.assertEqual(value, "old")
        self.assertIn("预览模式未修改数据库", result.logs[0])

    def test_writeback_execute_updates_sqlite(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            db_path = str(Path(temp_dir) / "run_writeback.db")
            conn = sqlite3.connect(db_path)
            try:
                conn.execute('CREATE TABLE target (id TEXT, value TEXT)')
                conn.execute('INSERT INTO target (id, value) VALUES (?, ?)', ("A", "old"))
                conn.commit()
            finally:
                conn.close()

            engine = HeadlessWorkflowEngine(services=WorkflowServices(db_path=db_path))
            plan = {
                "nodes": [{
                    "node_type_id": "core.writeback",
                    "config": {
                        "enable_write": True,
                        "target_table": "target",
                        "use_match_rules": True,
                        "match_rules": [{"source_field": "id", "target_field": "id", "operator": "等于"}],
                        "field_mappings": [{"source_field": "value", "target_field": "value"}],
                        "overwrite_policy": "覆盖全部",
                    },
                }],
                "headers": ["id", "value"],
                "rows": [["A", "new"]],
            }

            result = engine.run_plan(plan, execute_actions=True)
            conn = sqlite3.connect(db_path)
            try:
                value = conn.execute('SELECT value FROM target WHERE id=?', ("A",)).fetchone()[0]
            finally:
                conn.close()

        self.assertEqual(value, "new")
        self.assertIn("已写入目标表 target：1 处", result.logs[0])

    def test_writeback_external_table_to_current_uses_sqlite_source(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            db_path = str(Path(temp_dir) / "external_current.db")
            conn = sqlite3.connect(db_path)
            try:
                conn.execute('CREATE TABLE source (name TEXT)')
                conn.execute('INSERT INTO source (name) VALUES (?)', ("Alpha",))
                conn.commit()
            finally:
                conn.close()

            engine = HeadlessWorkflowEngine(services=WorkflowServices(db_path=db_path))
            plan = {
                "nodes": [{
                    "node_type_id": "core.writeback",
                    "config": {
                        "writeback_direction": "其他表写入当前表",
                        "source_table": "source",
                        "use_match_rules": False,
                        "field_mappings": [{"source_field": "name", "target_field": "external_name"}],
                        "overwrite_policy": "覆盖全部",
                    },
                }],
                "headers": ["id"],
                "rows": [["A"]],
            }

            result = engine.preview_plan(plan)

        self.assertEqual(result.headers, ["id", "external_name"])
        self.assertEqual(result.rows, [["A", "Alpha"]])
        self.assertIn("其他表写入当前表", result.logs[0])


if __name__ == "__main__":
    unittest.main()
