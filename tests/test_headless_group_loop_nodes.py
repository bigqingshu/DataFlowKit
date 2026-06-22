# -*- coding: utf-8 -*-
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from engine import HeadlessWorkflowEngine
from engine.workflow_services import WorkflowServices
from workflow.nodes.loop_nodes import LOOP_RESULT_HEADERS


class HeadlessLoopNodeTests(unittest.TestCase):
    def make_engine(self):
        ids = iter(["n1", "n2", "n3", "n4", "n5", "n6"])
        return HeadlessWorkflowEngine(
            node_id_factory=lambda: next(ids),
            now_factory=lambda: datetime(2026, 1, 2, 3, 4, 5),
        )

    def test_loop_start_and_judge_iterate_until_queue_is_done(self):
        engine = self.make_engine()
        plan = {
            "nodes": [
                {
                    "node_type_id": "core.loop_start",
                    "config": {
                        "loop_id": "L",
                        "fields": ["Name"],
                        "current_table_name": "当前项",
                    },
                },
                {
                    "node_type_id": "core.new_columns",
                    "config": {
                        "columns_text": "Done=ok",
                        "value_mode": "按列配置值",
                    },
                },
                {
                    "node_type_id": "core.loop_judge",
                    "config": {
                        "loop_id": "L",
                        "condition_mode": "始终成功",
                        "result_table_name": "循环结果",
                        "end_output_mode": "循环结果表",
                    },
                },
            ],
            "headers": ["Name"],
            "rows": [["A"], ["B"]],
        }

        result = engine.run_plan(plan)

        self.assertEqual(result.headers, LOOP_RESULT_HEADERS)
        self.assertEqual(len(result.rows), 2)
        self.assertEqual([row[2] for row in result.rows], ["1", "2"])
        self.assertEqual([row[4] for row in result.rows], ["完成2", "完成2"])
        self.assertEqual(result.steps, 6)
        self.assertEqual(result.pc, 3)
        self.assertEqual(result.context["loop_states"]["L"]["queue_rows"], [["2", "1", "A"], ["2", "2", "B"]])
        self.assertEqual(result.context["transit_tables"]["当前项"]["rows"], [["B"]])
        self.assertEqual(result.context["transit_tables"]["循环结果"]["rows"], result.rows)
        self.assertIn("循环队列_L", result.context["transit_tables"])

    def test_loop_start_skips_body_when_queue_is_empty(self):
        engine = self.make_engine()
        plan = {
            "nodes": [
                {
                    "type": "循环执行起点",
                    "config": {
                        "loop_id": "Empty",
                        "fields": ["Name"],
                        "current_table_name": "当前项",
                    },
                },
                {
                    "type": "新建列",
                    "config": {
                        "columns_text": "ShouldNotRun=x",
                        "value_mode": "按列配置值",
                    },
                },
                {
                    "type": "循环判断回跳",
                    "config": {"loop_id": "Empty"},
                },
            ],
            "headers": ["Name"],
            "rows": [],
        }

        result = engine.run_plan(plan)

        self.assertEqual(result.headers, ["Name"])
        self.assertEqual(result.rows, [])
        self.assertEqual(result.steps, 1)
        self.assertEqual(result.pc, 3)
        self.assertEqual(result.context["transit_tables"]["当前项"]["rows"], [])
        self.assertIn("无待执行项，跳过循环体", result.logs[0])

    def test_loop_start_can_read_transit_table_source(self):
        engine = self.make_engine()
        plan = {
            "nodes": [
                {
                    "node_type_id": "core.loop_start",
                    "config": {
                        "loop_id": "T",
                        "source_type": "中转副表",
                        "transit_table": "来源",
                        "fields": ["Name"],
                        "current_table_name": "当前项",
                    },
                },
                {
                    "node_type_id": "core.loop_judge",
                    "config": {
                        "loop_id": "T",
                        "condition_mode": "始终成功",
                        "end_output_mode": "循环队列表",
                    },
                },
            ]
        }

        result = engine.run_plan(
            plan,
            input_table={"headers": ["Unused"], "rows": [["x"]]},
            initial_context={
                "transit_tables": {
                    "来源": {"headers": ["Name"], "rows": [["A"]], "source": "测试"}
                }
            },
        )

        self.assertEqual(result.headers, ["执行标志", "原始行号", "Name"])
        self.assertEqual(result.rows, [["2", "1", "A"]])
        self.assertEqual(result.context["loop_states"]["T"]["source_name"], "中转:来源")
        self.assertTrue(
            any(log.get("operation") == "read_transit_table" for log in result.context["table_access_logs"])
        )

    def test_loop_nodes_are_reported_as_headless_supported(self):
        engine = self.make_engine()

        self.assertTrue(engine.is_node_supported("core.loop_start"))
        self.assertTrue(engine.is_node_supported("循环判断回跳"))
        self.assertIn("core.loop_judge", engine.list_node_type_ids(include_unsupported=False))


class HeadlessGroupNodeTests(unittest.TestCase):
    def make_engine(self):
        ids = iter([f"g{i}" for i in range(1, 20)])
        return HeadlessWorkflowEngine(
            node_id_factory=lambda: next(ids),
            now_factory=lambda: datetime(2026, 1, 2, 3, 4, 5),
        )

    def test_group_runs_inner_nodes_and_outputs_group_result(self):
        engine = self.make_engine()
        plan = {
            "nodes": [{
                "node_type_id": "core.group",
                "config": {
                    "group_name": "组A",
                    "input_fields": ["Name"],
                    "input_mapping": {"Name": "A"},
                    "nodes": [{
                        "node_type_id": "core.new_columns",
                        "config": {
                            "columns_text": "Done=ok",
                            "value_mode": "按列配置值",
                        },
                    }],
                },
            }],
            "headers": ["A"],
            "rows": [["alpha"], ["beta"]],
        }

        result = engine.run_plan(plan)

        self.assertEqual(result.headers, ["Name", "Done"])
        self.assertEqual(result.rows, [["alpha", "ok"], ["beta", "ok"]])
        self.assertEqual(result.steps, 1)
        self.assertIn("节点组【组A】完成", result.logs[0])
        self.assertIn("主输出=组结果作为当前表", result.logs[0])

    def test_group_can_passthrough_main_table_and_save_transit_output(self):
        engine = self.make_engine()
        plan = {
            "nodes": [{
                "type": "节点组 / 子工作流",
                "config": {
                    "group_name": "组B",
                    "main_output_mode": "透传原当前表",
                    "save_to_transit": True,
                    "output_transit_name": "组输出",
                    "nodes": [{
                        "type": "新建列",
                        "config": {
                            "columns_text": "Inner=1",
                            "value_mode": "按列配置值",
                        },
                    }],
                },
            }],
            "headers": ["A"],
            "rows": [["a"]],
        }

        result = engine.run_plan(plan)

        self.assertEqual(result.headers, ["A"])
        self.assertEqual(result.rows, [["a"]])
        self.assertEqual(result.context["transit_tables"]["组输出"]["headers"], ["A", "Inner"])
        self.assertEqual(result.context["transit_tables"]["组输出"]["rows"], [["a", "1"]])
        self.assertIn("主输出=透传原当前表", result.logs[0])

    def test_group_can_read_transit_source_and_expose_child_transit_when_allowed(self):
        engine = self.make_engine()
        plan = {
            "nodes": [{
                "node_type_id": "core.group",
                "config": {
                    "group_name": "组C",
                    "input_source_type": "中转副表",
                    "input_transit_table": "来源",
                    "transit_scope": "允许输出到外部",
                    "nodes": [{
                        "node_type_id": "core.save_transit",
                        "config": {
                            "transit_name": "组内保存",
                            "save_memory": True,
                        },
                    }],
                },
            }],
        }

        result = engine.run_plan(
            plan,
            initial_context={
                "transit_tables": {
                    "来源": {"headers": ["A"], "rows": [["from-transit"]], "source": "测试"}
                }
            },
        )

        self.assertEqual(result.headers, ["A"])
        self.assertEqual(result.rows, [["from-transit"]])
        self.assertIn("组内保存", result.context["transit_tables"])
        self.assertEqual(result.context["transit_tables"]["组内保存"]["rows"], [["from-transit"]])
        self.assertTrue(
            any(log.get("operation") == "read_transit_table" for log in result.context["table_access_logs"])
        )

    def test_group_sqlite_output_only_writes_when_execute_actions_is_true(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as temp_dir:
            db_path = str(Path(temp_dir) / "group.db")
            engine = HeadlessWorkflowEngine(
                services=WorkflowServices(db_path=db_path),
                now_factory=lambda: datetime(2026, 1, 2, 3, 4, 5),
            )
            plan = {
                "nodes": [{
                    "node_type_id": "core.group",
                    "config": {
                        "group_name": "组D",
                        "save_to_sqlite": True,
                        "output_sqlite_table": "group_out",
                        "output_sqlite_mode": "覆盖表",
                        "nodes": [{
                            "node_type_id": "core.new_columns",
                            "config": {
                                "columns_text": "B=b",
                                "value_mode": "按列配置值",
                            },
                        }],
                    },
                }],
                "headers": ["A"],
                "rows": [["a"]],
            }

            preview = engine.preview_plan(plan)
            self.assertFalse(os.path.exists(db_path))

            executed = engine.run_plan(plan, execute_actions=True)
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute('SELECT "A", "B" FROM "group_out"').fetchall()
            finally:
                conn.close()

        self.assertEqual(preview.headers, ["A", "B"])
        self.assertEqual(executed.headers, ["A", "B"])
        self.assertEqual(rows, [("a", "b")])
        self.assertIn("SQLite表：group_out（1行）", executed.logs[0])

    def test_group_rejects_inner_loop_nodes(self):
        engine = self.make_engine()
        plan = {
            "nodes": [{
                "node_type_id": "core.group",
                "config": {
                    "group_name": "组E",
                    "nodes": [{
                        "node_type_id": "core.loop_start",
                        "config": {"loop_id": "L"},
                    }],
                },
            }],
            "headers": ["A"],
            "rows": [["a"]],
        }

        validation = engine.validate_plan(plan)

        self.assertFalse(validation["ok"])
        self.assertEqual(validation["issues"][0]["code"], "unsupported_group_loop_node")

    def test_group_node_is_reported_as_headless_supported(self):
        engine = self.make_engine()

        self.assertTrue(engine.is_node_supported("core.group"))
        self.assertIn("core.group", engine.list_node_type_ids(include_unsupported=False))


if __name__ == "__main__":
    unittest.main()
