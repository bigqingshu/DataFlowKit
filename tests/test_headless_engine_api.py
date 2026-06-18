# -*- coding: utf-8 -*-
import threading
import unittest
from datetime import datetime

from engine import HeadlessWorkflowEngine, PlanValidationError, TableData


class HeadlessWorkflowEngineApiTests(unittest.TestCase):
    def make_engine(self):
        ids = iter(["n1", "n2", "n3", "n4", "n5"])
        return HeadlessWorkflowEngine(
            node_id_factory=lambda: next(ids),
            now_factory=lambda: datetime(2026, 1, 2, 3, 4, 5),
        )

    def test_table_payload_roundtrip(self):
        table = TableData.from_payload({"type": "table", "headers": ["A"], "rows": [["x"], ["y"]]})

        self.assertEqual(table.headers, ["A"])
        self.assertEqual(table.rows, [["x"], ["y"]])
        self.assertEqual(table.to_dict(), {"type": "table", "headers": ["A"], "rows": [["x"], ["y"]]})

    def test_node_catalog_and_default_node_are_ui_free(self):
        engine = self.make_engine()

        self.assertIn("新建列", engine.list_node_types(include_unsupported=False))
        self.assertNotIn("插件节点", engine.list_node_types(include_unsupported=False))

        schema = engine.get_node_schema("新建列", preview_headers=["A"])
        node = engine.make_default_node("新建列", preview_headers=["A"])

        self.assertTrue(schema["supported"])
        self.assertIn("columns_text", schema["default_config"])
        self.assertEqual(node["node_id"], "n1")
        self.assertEqual(node["type"], "新建列")
        self.assertTrue(node["enabled"])

    def test_validate_plan_reports_unsupported_nodes_without_running(self):
        engine = self.make_engine()
        validation = engine.validate_plan({
            "nodes": [
                {"type": "新建列", "config": {"columns_text": "B"}},
                {"type": "插件节点", "config": {"plugin_id": "demo"}},
                {"type": "高级筛选", "enabled": False, "config": {}},
            ]
        })

        self.assertFalse(validation["ok"])
        self.assertEqual(validation["issues"][0]["code"], "unsupported_node")
        self.assertEqual(validation["issues"][1]["code"], "disabled_unsupported_node")

        with self.assertRaises(PlanValidationError) as cm:
            engine.run_plan({"nodes": [{"type": "插件节点", "config": {}}]})
        self.assertEqual(cm.exception.issues[0]["node_type"], "插件节点")

    def test_preview_plan_runs_basic_data_nodes(self):
        engine = self.make_engine()
        plan = {
            "nodes": [
                {
                    "type": "新建列",
                    "config": {
                        "columns_text": "B=b",
                        "value_mode": "按列配置值",
                    },
                },
                {
                    "type": "批量替换",
                    "config": {
                        "target_field": "B",
                        "match_mode": "包含",
                        "replace_mode": "局部替换匹配字符串",
                        "match_value": "b",
                        "replace_value": "c",
                    },
                },
            ],
        }

        events = []
        result = engine.preview_plan(
            plan,
            input_table={"headers": ["A"], "rows": [["a1"], ["a2"]]},
            progress_callback=events.append,
        )

        self.assertNotIn("node_id", plan["nodes"][0])
        self.assertEqual(result.headers, ["A", "B"])
        self.assertEqual(result.rows, [["a1", "c"], ["a2", "c"]])
        self.assertEqual(result.steps, 2)
        self.assertEqual(result.pc, 2)
        self.assertEqual(events[0]["type"], "workflow_start")
        self.assertEqual(events[-1]["type"], "workflow_done")
        self.assertIn("新建列完成", result.logs[0])
        self.assertIn("修改 2 处", result.logs[1])

    def test_stop_index_previews_prefix_only(self):
        engine = self.make_engine()
        plan = {
            "nodes": [
                {"type": "新建列", "config": {"columns_text": "B=b", "value_mode": "按列配置值"}},
                {"type": "新建列", "config": {"columns_text": "C=c", "value_mode": "按列配置值"}},
            ],
            "headers": ["A"],
            "rows": [["a"]],
        }

        result = engine.preview_plan(plan, stop_index=0)

        self.assertEqual(result.headers, ["A", "B"])
        self.assertEqual(result.rows, [["a", "b"]])
        self.assertEqual(result.pc, 1)

    def test_condition_jump_skips_nodes(self):
        engine = self.make_engine()
        plan = {
            "nodes": [
                {
                    "type": "条件判断节点",
                    "config": {
                        "flag_name": "has_rows",
                        "condition_type": "表行数",
                        "op": "大于",
                        "value": "0",
                        "true_value": "TRUE",
                        "false_value": "FALSE",
                    },
                },
                {
                    "type": "条件跳转节点",
                    "config": {
                        "flag_name": "has_rows",
                        "jump_rules": [{"value": "TRUE", "target_anchor_id": "end"}],
                    },
                },
                {"type": "新建列", "config": {"columns_text": "Skipped=x", "value_mode": "按列配置值"}},
                {"type": "跳转锚点节点", "config": {"anchor_id": "end", "anchor_name": "结束"}},
                {"type": "新建列", "config": {"columns_text": "Done=y", "value_mode": "按列配置值"}},
            ],
            "headers": ["A"],
            "rows": [["a"]],
        }

        result = engine.run_plan(plan)

        self.assertEqual(result.headers, ["A", "Done"])
        self.assertEqual(result.rows, [["a", "y"]])
        self.assertEqual(result.context["condition_flags"]["has_rows"]["value"], "TRUE")
        self.assertGreaterEqual(len(result.context["jump_logs"]), 3)

    def test_cancel_event_stops_before_running_nodes(self):
        engine = self.make_engine()
        cancel = threading.Event()
        cancel.set()

        result = engine.run_plan(
            {"nodes": [{"type": "新建列", "config": {"columns_text": "B"}}]},
            input_table={"headers": ["A"], "rows": [["a"]]},
            cancel_event=cancel,
        )

        self.assertTrue(result.cancelled)
        self.assertEqual(result.headers, ["A"])
        self.assertEqual(result.rows, [["a"]])
        self.assertEqual(result.steps, 0)
        self.assertEqual(result.logs, ["用户取消后台执行，工作流已安全停止。"])


if __name__ == "__main__":
    unittest.main()
