# -*- coding: utf-8 -*-
import types
import unittest

from DataFlowKit import PlanWorkflowWindow
from workflow.nodes.plugin_nodes import (
    build_plugin_failure_output,
    build_plugin_final_output,
    build_plugin_probe_final_output,
    build_plugin_probe_stat,
    build_plugin_status_text,
    get_plugin_output_schema_table,
    is_external_plugin_mode,
    make_plugin_input_data,
    merge_plugin_output_fields_to_current,
    normalize_plugin_logs,
    normalize_plugin_output_schema,
    normalize_plugin_run_result,
    plugin_log_items_to_table,
    should_save_plugin_output_as_transit,
)


class WorkflowPluginNodesTests(unittest.TestCase):
    def make_plugin_window(self, module, plugin_id="test_plugin"):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        window.plugin_registry = {
            plugin_id: {
                "module": module,
                "info": {"id": plugin_id, "name": "测试插件"},
            }
        }
        window.build_plugin_input_tables = lambda config, headers, rows, context=None: {
            "当前表": {"type": "table", "headers": list(headers), "rows": [list(r) for r in rows]},
            "workflow_current": {"type": "table", "headers": list(headers), "rows": [list(r) for r in rows]},
            "primary": {"type": "table", "headers": list(headers), "rows": [list(r) for r in rows]},
        }
        window.make_plugin_context = lambda config, context=None, execute_actions=False: {
            "is_preview": not execute_actions,
            "execute_actions": execute_actions,
        }
        window.save_plugin_output_to_transit = lambda *args, **kwargs: "中转副表：测试输出"
        window.save_plugin_logs_to_file = lambda *args, **kwargs: ""
        window.save_plugin_logs_to_sqlite = lambda *args, **kwargs: 0
        return window

    def test_dataflowkit_apply_plugin_node_uses_returned_output(self):
        module = types.SimpleNamespace(
            run=lambda input_data, params, context: {
                "ok": True,
                "message": "done",
                "logs": [{"message": "log"}],
                "summary": {"rows": 1},
                "output": {"type": "table", "headers": ["B"], "rows": [["b"]]},
            }
        )
        window = self.make_plugin_window(module)

        headers, rows, stat = window.apply_plugin_node(
            ["A"],
            [["a"]],
            {"plugin_id": "test_plugin", "params": {}, "output_mode": "使用插件返回结果"},
            context={},
        )

        self.assertEqual(headers, ["B"])
        self.assertEqual(rows, [["b"]])
        self.assertIn("插件 测试插件 完成", stat)
        self.assertIn("done", stat)
        self.assertIn("log", stat)

    def test_dataflowkit_apply_plugin_node_can_append_output_fields(self):
        module = types.SimpleNamespace(
            run=lambda input_data, params, context: {
                "type": "table",
                "headers": ["A", "B"],
                "rows": [["new-a", "b"]],
            }
        )
        window = self.make_plugin_window(module)

        headers, rows, _stat = window.apply_plugin_node(
            ["A"],
            [["old-a"]],
            {"plugin_id": "test_plugin", "params": {}, "output_mode": "追加字段到当前表"},
            context={},
        )

        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["new-a", "b"]])

    def test_dataflowkit_apply_plugin_node_failure_policies(self):
        module = types.SimpleNamespace(run=lambda input_data, params, context: (_ for _ in ()).throw(RuntimeError("boom")))
        window = self.make_plugin_window(module)

        headers, rows, stat = window.apply_plugin_node(
            ["A"],
            [["a"]],
            {"plugin_id": "test_plugin", "params": {}, "plugin_failure_policy": "保留原表继续"},
            context={},
        )
        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["a"]])
        self.assertIn("失败处理：保留原表继续", stat)

        headers, rows, stat = window.apply_plugin_node(
            ["A"],
            [["a"]],
            {"plugin_id": "test_plugin", "params": {}, "plugin_failure_policy": "输出错误表继续"},
            context={},
        )
        self.assertEqual(headers, ["插件ID", "错误信息", "错误堆栈"])
        self.assertEqual(rows[0][:2], ["test_plugin", "boom"])
        self.assertIn("失败处理：输出错误表继续", stat)

    def test_normalize_plugin_logs_accepts_strings_bytes_and_dicts(self):
        logs = normalize_plugin_logs(
            ["hello", b"bytes", {"level": "warning", "msg": "dict msg"}],
            plugin_id="p1",
            node_name="node",
            now_text="2026-01-01 00:00:00",
        )

        self.assertEqual([item["message"] for item in logs], ["hello", "b'bytes'", "dict msg"])
        self.assertEqual([item["level"] for item in logs], ["INFO", "INFO", "WARNING"])
        self.assertEqual(logs[0]["plugin_id"], "p1")
        self.assertEqual(logs[0]["node_name"], "node")
        self.assertEqual(logs[0]["time"], "2026-01-01 00:00:00")

    def test_plugin_log_items_to_table_projects_rows(self):
        headers, rows = plugin_log_items_to_table([
            {
                "time": "t",
                "level": "INFO",
                "plugin_id": "p",
                "node_name": "n",
                "object": "o",
                "message": "m",
                "traceback": "tb",
            }
        ])

        self.assertEqual(headers, ["时间", "级别", "插件ID", "节点名称", "对象", "信息", "错误堆栈"])
        self.assertEqual(rows, [["t", "INFO", "p", "n", "o", "m", "tb"]])

    def test_merge_plugin_output_fields_to_current_overwrites_same_name_by_row(self):
        headers, rows = merge_plugin_output_fields_to_current(
            ["A", "B"],
            [["a1", "b1"], ["a2"]],
            ["B", "C"],
            [["new-b1", "c1"], ["new-b2", "c2"], ["new-b3", "c3"]],
        )

        self.assertEqual(headers, ["A", "B", "C"])
        self.assertEqual(rows, [["a1", "new-b1", "c1"], ["a2", "new-b2", "c2"], ["", "new-b3", "c3"]])

    def test_normalize_plugin_output_schema_supports_common_shapes(self):
        self.assertEqual(
            normalize_plugin_output_schema(["A", 2]),
            {"type": "table", "headers": ["A", "2"], "rows": [], "meta": {"lazy_schema": True}},
        )
        self.assertEqual(
            normalize_plugin_output_schema({"fields": ["A"], "rows": [["x"]], "meta": {"m": 1}}),
            {"type": "table", "headers": ["A"], "rows": [["x"]], "meta": {"m": 1, "lazy_schema": True}},
        )
        self.assertEqual(
            normalize_plugin_output_schema({"output": {"columns": ["C"]}}, fallback_headers=["F"])["headers"],
            ["C"],
        )
        self.assertIsNone(normalize_plugin_output_schema("invalid"))

    def test_get_plugin_output_schema_table_prefers_provider_then_info(self):
        module = types.SimpleNamespace(get_output_schema=lambda params, input_data, context: {"headers": [params["field"]]})
        item = {"module": module, "info": {"output_headers": ["fallback"]}}
        self.assertEqual(get_plugin_output_schema_table(item, {}, {"field": "from_provider"}, {})["headers"], ["from_provider"])

        item = {"module": types.SimpleNamespace(), "info": {"output_headers": ["from_info"]}}
        self.assertEqual(get_plugin_output_schema_table(item, {}, {}, {})["headers"], ["from_info"])

    def test_normalize_plugin_run_result_validates_and_extracts_output(self):
        result = normalize_plugin_run_result(
            {
                "ok": True,
                "message": "done",
                "logs": ["log"],
                "summary": {"n": 1},
                "output": {"type": "table", "headers": ["B"], "rows": [["b"]]},
            },
            {"type": "table", "headers": ["A"], "rows": [["a"]]},
            ["A"],
            [["a"]],
        )

        self.assertEqual(result["message"], "done")
        self.assertEqual(result["headers"], ["B"])
        self.assertEqual(result["rows"], [["b"]])
        with self.assertRaisesRegex(RuntimeError, "bad"):
            normalize_plugin_run_result({"ok": False, "message": "bad"}, {}, [], [])
        with self.assertRaisesRegex(ValueError, "插件返回值必须"):
            normalize_plugin_run_result("bad", {}, [], [])

    def test_final_output_modes_and_transit_flag(self):
        self.assertTrue(should_save_plugin_output_as_transit({"output_mode": "保存为中转副表并使用插件返回结果"}))
        self.assertTrue(should_save_plugin_output_as_transit({"save_output_as_transit": True}))
        self.assertFalse(should_save_plugin_output_as_transit({"output_mode": "使用插件返回结果"}))

        self.assertEqual(
            build_plugin_final_output(["A"], [["a"]], ["B"], [["b"]], "保存为中转副表并保持当前表"),
            (["A"], [["a"]]),
        )
        self.assertEqual(
            build_plugin_final_output(["A"], [["a"]], ["B"], [["b"]], "使用插件返回结果"),
            (["B"], [["b"]]),
        )
        self.assertEqual(
            build_plugin_probe_final_output(["A"], [["a"]], ["B"], [], "追加字段到当前表", True),
            (["A", "B"], []),
        )

    def test_failure_output_and_status_text(self):
        headers, rows = build_plugin_failure_output("p", "err", "trace", ["A"], [["a"]], "输出错误表继续")
        self.assertEqual(headers, ["插件ID", "错误信息", "错误堆栈"])
        self.assertEqual(rows, [["p", "err", "trace"]])
        self.assertEqual(build_plugin_failure_output("p", "err", "trace", ["A"], [["a"]], "保留原表继续"), (["A"], [["a"]]))

        stat = build_plugin_status_text(
            "插件名",
            "p",
            False,
            "输出错误表继续",
            "err",
            {"n": 1},
            ["中转副表：out"],
            ["日志文件：log"],
            [{"message": "log msg"}],
        )
        self.assertIn("插件 插件名 完成", stat)
        self.assertIn("失败处理：输出错误表继续", stat)
        self.assertIn("摘要:", stat)
        self.assertIn("log msg", stat)

    def test_probe_stat_and_external_mode(self):
        self.assertEqual(
            build_plugin_probe_stat("插件", True, ["A", "B"], ["中转副表：x"]),
            "插件 插件 字段懒加载：未执行插件，已返回 2 个字段；中转副表：x",
        )
        self.assertEqual(
            build_plugin_probe_stat("插件", False, ["A"], []),
            "插件 插件 字段懒加载：插件未声明输出字段，暂按上游字段透传",
        )
        self.assertTrue(is_external_plugin_mode({"run_mode": "插件独立环境"}))
        self.assertTrue(is_external_plugin_mode({}, {"run_mode_default": "插件独立环境"}))
        self.assertFalse(is_external_plugin_mode({"run_mode": "主程序内置环境"}))

    def test_make_plugin_input_data_keeps_table_shape(self):
        data = make_plugin_input_data("p", ["A"], [["a"]], {"primary": {"headers": ["A"]}}, lazy_schema=True)
        self.assertEqual(data["meta"], {"plugin_id": "p", "lazy_schema": True})
        self.assertEqual(data["tables"]["primary"]["headers"], ["A"])


if __name__ == "__main__":
    unittest.main()
