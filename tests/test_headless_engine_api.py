# -*- coding: utf-8 -*-
import threading
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from db.table_manager import TableAccessManager
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
        self.assertIn("core.new_columns", engine.list_node_type_ids(include_unsupported=False))
        self.assertNotIn("插件节点", engine.list_node_types(include_unsupported=False))
        self.assertNotIn("core.plugin", engine.list_node_type_ids(include_unsupported=False))

        schema = engine.get_node_schema("core.new_columns", preview_headers=["A"])
        node = engine.make_default_node("新建列", preview_headers=["A"])
        protocol_node = engine.make_default_node(
            "core.new_columns",
            preview_headers=["A"],
            include_legacy_type=False,
        )

        self.assertEqual(schema["node_type_id"], "core.new_columns")
        self.assertEqual(schema["display_name"], "新建列")
        self.assertTrue(schema["supported"])
        self.assertIn("columns_text", schema["default_config"])
        self.assertEqual(node["node_id"], "n1")
        self.assertEqual(node["node_type_id"], "core.new_columns")
        self.assertEqual(node["type"], "新建列")
        self.assertTrue(node["enabled"])
        self.assertEqual(protocol_node["node_id"], "n2")
        self.assertEqual(protocol_node["node_type_id"], "core.new_columns")
        self.assertNotIn("type", protocol_node)

    def test_node_ui_schema_is_available_without_qt_imports(self):
        engine = self.make_engine()

        schemas = engine.list_node_ui_schemas(include_unsupported=False, preview_headers=["A"])
        schema = engine.get_node_ui_schema("core.new_columns", preview_headers=["A"])

        self.assertTrue(schemas)
        self.assertIn("core.new_columns", [item["node_type_id"] for item in schemas])
        self.assertEqual(schema["node_type_id"], "core.new_columns")
        self.assertEqual(schema["display_name"], "新建列")
        self.assertEqual(schema["menu"]["path"], ["数据处理", "新建列"])
        self.assertTrue(schema["capabilities"]["headless_preview"])
        self.assertIn("添加字段", schema["summary"])
        self.assertIn("columns_text", schema["default_config"])
        field_keys = [
            field["key"]
            for group in schema["form"]["groups"]
            for field in group["fields"]
        ]
        self.assertIn("columns_text", field_keys)

    def test_node_ui_schema_carries_shared_warning_and_context_metadata(self):
        engine = self.make_engine()

        loop_schema = engine.get_node_ui_schema("core.loop_judge", preview_headers=["A"])
        self.assertTrue(loop_schema["warning_items"])
        self.assertEqual(loop_schema["warning_items"][0]["level"], "warning")

        loop_fields = {
            field["key"]: field
            for group in loop_schema["form"]["groups"]
            for field in group["fields"]
        }
        self.assertEqual(loop_fields["loop_id"]["context_requirements"][0]["kind"], "plan_refs")
        self.assertEqual(loop_fields["loop_id"]["context_requirements"][0]["ref_kind"], "loop_id")

        write_schema = engine.get_node_ui_schema(
            "字段映射写入表",
            preview_headers=["源字段"],
            table_names=["orders", "result"],
            table_columns={"orders": ["id", "name"], "result": ["row_id", "status"]},
        )
        write_fields = {
            field["key"]: field
            for group in write_schema["form"]["groups"]
            for field in group["fields"]
        }
        mapping_columns = {
            item["key"]: item
            for item in write_fields["field_mappings"]["item_schema"]["columns"]
        }
        self.assertEqual(mapping_columns["source_field"]["context_requirements"][0]["kind"], "table_columns")
        self.assertEqual(mapping_columns["source_field"]["context_requirements"][1]["field"], "source_table")

    def test_validate_plan_reports_unsupported_nodes_without_running(self):
        engine = self.make_engine()
        validation = engine.validate_plan({
            "nodes": [
                {"type": "新建列", "config": {"columns_text": "B"}},
                {"type": "插件节点", "config": {"plugin_id": "demo"}},
                {"type": "插件节点", "enabled": False, "config": {"plugin_id": "disabled_demo"}},
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
        self.assertIn("elapsed_seconds", events[-1])

    def test_filter_node_loads_sqlite_extra_table_from_context_db_path(self):
        engine = self.make_engine()
        with TemporaryDirectory() as temp_dir:
            db_path = str(Path(temp_dir) / "input.db")
            TableAccessManager(db_path).write_table(
                "lookup",
                ["Code", "Name"],
                [["A", "Alpha"], ["C", "Gamma"]],
                mode="replace",
            )
            plan = {
                "nodes": [
                    {
                        "node_type_id": "core.filter",
                        "config": {
                            "conditions": [],
                            "join_rules": [{"left": "当前表.Code", "op": "等于", "right": "lookup.Code"}],
                            "extra_tables": ["lookup"],
                            "output_fields": ["当前表.Code", "lookup.Name"],
                        },
                    },
                ],
            }
            events = []

            result = engine.preview_plan(
                plan,
                input_table={"headers": ["Code"], "rows": [["A"], ["B"]]},
                initial_context={"workflow_snapshot": {"db_path": db_path}},
                progress_callback=events.append,
            )

            self.assertEqual(result.headers, ["Code", "lookup.Name"])
            self.assertEqual(result.rows, [["A", "Alpha"]])
            done_event = next(item for item in events if item.get("type") == "node_done")
            self.assertIn("elapsed_seconds", done_event)
            self.assertGreaterEqual(done_event["elapsed_seconds"], 0)

    def test_preview_plan_runs_node_type_id_only_nodes(self):
        engine = self.make_engine()
        plan = {
            "nodes": [
                {
                    "node_type_id": "core.new_columns",
                    "enabled": True,
                    "config": {
                        "columns_text": "B=b",
                        "value_mode": "按列配置值",
                    },
                },
                {
                    "node_type_id": "core.replace",
                    "enabled": True,
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
            input_table={"type": "table", "headers": ["A"], "rows": [["a"]]},
            progress_callback=events.append,
        )

        self.assertEqual(result.headers, ["A", "B"])
        self.assertEqual(result.rows, [["a", "c"]])
        self.assertEqual(result.context["current_node_info"]["node_type_id"], "core.replace")
        self.assertEqual(events[1]["node_type_id"], "core.new_columns")
        self.assertIn("新建列", result.logs[0])

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
                    "node_type_id": "core.condition_check",
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
                    "node_type_id": "core.conditional_jump",
                    "config": {
                        "flag_name": "has_rows",
                        "jump_rules": [{"value": "TRUE", "target_anchor_id": "end"}],
                    },
                },
                {"node_type_id": "core.new_columns", "config": {"columns_text": "Skipped=x", "value_mode": "按列配置值"}},
                {"node_type_id": "core.jump_anchor", "config": {"anchor_id": "end", "anchor_name": "结束"}},
                {"node_type_id": "core.new_columns", "config": {"columns_text": "Done=y", "value_mode": "按列配置值"}},
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
