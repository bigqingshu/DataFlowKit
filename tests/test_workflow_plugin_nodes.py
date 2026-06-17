# -*- coding: utf-8 -*-
import types
import unittest

from DataFlowKit import PlanWorkflowWindow
from workflow import plugin_node_runtime
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

    def test_dataflowkit_run_plugin_node_runtime_validates_then_runs_internal_plugin(self):
        calls = []

        def validate(params, input_data, context):
            calls.append(("validate", params.get("p"), input_data["headers"], context["execute_actions"]))
            return True, ""

        def run(input_data, params, context):
            calls.append(("run", params.get("p"), input_data["rows"], context["execute_actions"]))
            return {
                "ok": True,
                "output": {"type": "table", "headers": ["B"], "rows": [["b"]]},
            }

        module = types.SimpleNamespace(validate_params=validate, run=run)
        window = self.make_plugin_window(module)
        item = window.plugin_registry["test_plugin"]
        runtime_context = {}

        normalized, plugin_context, input_data = window.run_plugin_node_runtime(
            ["A"],
            [["a"]],
            {"plugin_id": "test_plugin"},
            item,
            {"p": "x"},
            runtime_context,
            execute_actions=True,
        )

        self.assertEqual(calls, [
            ("validate", "x", ["A"], True),
            ("run", "x", [["a"]], True),
        ])
        self.assertEqual(normalized["headers"], ["B"])
        self.assertEqual(normalized["rows"], [["b"]])
        self.assertTrue(plugin_context["execute_actions"])
        self.assertEqual(input_data["tables"]["primary"]["headers"], ["A"])
        self.assertIn("input_tables", runtime_context)

    def test_dataflowkit_run_plugin_node_runtime_validation_failure_raises(self):
        module = types.SimpleNamespace(
            validate_params=lambda params, input_data, context: (False, "bad params"),
            run=lambda input_data, params, context: self.fail("run should not be called"),
        )
        window = self.make_plugin_window(module)
        item = window.plugin_registry["test_plugin"]

        with self.assertRaisesRegex(ValueError, "bad params"):
            window.run_plugin_node_runtime(
                ["A"],
                [["a"]],
                {"plugin_id": "test_plugin"},
                item,
                {},
                {},
            )

    def test_dataflowkit_run_plugin_node_runtime_dispatches_external_plugin(self):
        window = self.make_plugin_window(None)
        item = window.plugin_registry["test_plugin"]
        calls = []

        def fake_run_external(item_arg, input_data, params, config, context, execute_actions=False):
            calls.append((item_arg is item, input_data["headers"], params, config["run_mode"], execute_actions))
            return {
                "ok": True,
                "output": {"type": "table", "headers": ["OUT"], "rows": [["ok"]]},
            }

        window.run_external_plugin_process = fake_run_external

        normalized, plugin_context, _input_data = window.run_plugin_node_runtime(
            ["A"],
            [["a"]],
            {"plugin_id": "test_plugin", "run_mode": "插件独立环境"},
            item,
            {"p": 1},
            {},
            execute_actions=False,
        )

        self.assertEqual(calls, [(True, ["A"], {"p": 1}, "插件独立环境", False)])
        self.assertEqual(normalized["headers"], ["OUT"])
        self.assertEqual(normalized["rows"], [["ok"]])
        self.assertFalse(plugin_context["execute_actions"])

    def test_plugin_runtime_helpers_do_not_depend_on_window_runtime_wrappers(self):
        module = types.SimpleNamespace(
            run=lambda input_data, params, context: {
                "ok": True,
                "output": {"type": "table", "headers": ["B"], "rows": [[params["p"]]]},
            }
        )
        window = self.make_plugin_window(module)

        def legacy_wrapper_should_not_be_called(*_args, **_kwargs):
            raise AssertionError("plugin runtime should call lower-level window capabilities directly")

        window.apply_plugin_node = legacy_wrapper_should_not_be_called
        window.run_plugin_node_runtime = legacy_wrapper_should_not_be_called
        window.apply_lazy_plugin_probe_node = legacy_wrapper_should_not_be_called

        headers, rows, stat = plugin_node_runtime.apply_plugin_node_for_window(
            window,
            ["A"],
            [["a"]],
            {"plugin_id": "test_plugin", "params": {"p": "ok"}},
            context={},
        )

        self.assertEqual(headers, ["B"])
        self.assertEqual(rows, [["ok"]])
        self.assertIn("插件 测试插件 完成", stat)

    def test_plugin_runtime_config_probe_uses_declared_schema_without_run(self):
        module = types.SimpleNamespace(
            get_output_schema=lambda params, input_data, context: {"headers": ["Declared"]},
            run=lambda input_data, params, context: self.fail("config probe should not run plugin"),
        )
        window = self.make_plugin_window(module)
        window.build_plugin_probe_input_tables = lambda config, headers, context=None: {
            "当前表": {"type": "table", "headers": list(headers), "rows": []}
        }
        item = window.plugin_registry["test_plugin"]
        context = {"is_config_probe": True}

        headers, rows, stat = plugin_node_runtime.apply_plugin_node_for_window(
            window,
            ["A"],
            [["a"]],
            {"plugin_id": "test_plugin", "params": {}},
            context=context,
        )

        self.assertEqual(headers, ["Declared"])
        self.assertEqual(rows, [])
        self.assertIn("字段懒加载", stat)

    def test_dataflowkit_plugin_config_dynamic_choices_uses_provider_context(self):
        calls = []

        def provider(key, params, context):
            calls.append((key, params, context))
            return {"choices": [context["input_table_headers"]["当前表"][0], params["p"]]}

        module = types.SimpleNamespace(get_dynamic_parameter_options=provider)
        window = self.make_plugin_window(module)
        window.build_plugin_input_table_headers = lambda config, headers, context=None: {
            "当前表": list(headers),
            "primary": list(headers),
        }
        item = window.plugin_registry["test_plugin"]

        choices = window.get_plugin_dynamic_parameter_choices_for_config(
            item,
            {"plugin_id": "test_plugin", "input_tables": [{"alias": "extra"}]},
            {"p": 7},
            {"options": ["fallback"]},
            "field",
            ["A"],
            current_rows=[["a"]],
            transit_context={},
        )

        self.assertEqual(choices, ["A", "7"])
        self.assertEqual(calls[0][0], "field")
        self.assertEqual(calls[0][1], {"p": 7})
        self.assertIn("input_tables", calls[0][2])
        self.assertEqual(calls[0][2]["plugin_input_table_specs"], [{"alias": "extra"}])

    def test_dataflowkit_plugin_config_dynamic_choices_falls_back_on_error(self):
        module = types.SimpleNamespace(get_dynamic_parameter_options=lambda *args: (_ for _ in ()).throw(RuntimeError("bad")))
        window = self.make_plugin_window(module)
        window.build_plugin_input_table_headers = lambda config, headers, context=None: {"当前表": list(headers)}
        item = window.plugin_registry["test_plugin"]

        choices = window.get_plugin_dynamic_parameter_choices_for_config(
            item,
            {"plugin_id": "test_plugin"},
            {},
            {"choices": ["fallback"]},
            "field",
            ["A"],
        )

        self.assertEqual(choices, ["fallback"])

    def test_dataflowkit_run_plugin_custom_config_window_updates_params_and_controls(self):
        module = types.SimpleNamespace()
        window = self.make_plugin_window(module)
        window.window = object()
        window.status_messages = []
        window.status_var = types.SimpleNamespace(set=lambda text: window.status_messages.append(text))
        window.plugin_config_context_with_live_transit = lambda context=None, include_rows=False: {
            "transit_tables": {},
            "_reused_preview_transit_tables": ["tmp"],
        }
        window.build_plugin_input_tables = lambda config, headers, rows, context=None: {"当前表": {"headers": list(headers), "rows": rows}}
        refresh_calls = []

        class Var:
            def __init__(self):
                self.value = None

            def set(self, value):
                self.value = value

        field_var = Var()

        def open_config(parent, params, context):
            self.assertIs(parent, window.window)
            self.assertEqual(params, {"old": "value"})
            self.assertIn("plugin_config_data_note", context)
            self.assertIn("input_tables", context)
            return {"field": "B", "other": "C"}

        module.open_config_window = open_config
        item = {"module": module}
        config = {"params": {"old": "value"}, "input_tables": []}
        params = config["params"]

        changed = window.run_plugin_custom_config_window(
            item,
            config,
            params,
            ["A"],
            current_rows=[["a"]],
            transit_context={},
            dynamic_param_controls=[{"key": "field", "var": field_var}],
            refresh_dynamic_controls=lambda: refresh_calls.append(True),
        )

        self.assertTrue(changed)
        self.assertEqual(params, {"field": "B", "other": "C"})
        self.assertEqual(field_var.value, "B")
        self.assertEqual(refresh_calls, [True])
        self.assertIn("tmp", window.status_messages[0])

    def test_dataflowkit_refresh_plugin_dynamic_config_controls_updates_combo_and_param(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        params = {}

        class Var:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        class Combo:
            def __init__(self):
                self.values = None

            def configure(self, **kwargs):
                self.values = kwargs.get("values")

        var = Var("missing")
        combo = Combo()
        controls = [{
            "type": "input_table_select",
            "spec": {},
            "key": "table",
            "var": var,
            "combo": combo,
        }]

        window.refresh_plugin_dynamic_config_controls(
            controls,
            lambda key, value: params.__setitem__(key, value),
            lambda control: ["当前表", "明细"],
        )

        self.assertEqual(combo.values, ["当前表", "明细"])
        self.assertEqual(var.get(), "当前表")
        self.assertEqual(params, {"table": "当前表"})

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

    def test_dataflowkit_apply_plugin_node_reports_saved_log_and_transit_outputs(self):
        module = types.SimpleNamespace(
            run=lambda input_data, params, context: {
                "ok": True,
                "logs": [{"message": "log"}],
                "output": {"type": "table", "headers": ["B"], "rows": [["b"]]},
            }
        )
        window = self.make_plugin_window(module)
        transit_calls = []
        window.save_plugin_logs_to_file = lambda plugin_id, log_items: "plugin.log"
        window.save_plugin_logs_to_sqlite = lambda log_items, db_path=None, context=None: 2

        def fake_save_transit(context, name, headers, rows, conflict_mode="覆盖", source="插件输出"):
            transit_calls.append((name, source, headers, rows))
            return f"中转副表：{name}"

        window.save_plugin_output_to_transit = fake_save_transit

        headers, rows, stat = window.apply_plugin_node(
            ["A"],
            [["a"]],
            {
                "plugin_id": "test_plugin",
                "params": {},
                "save_plugin_log_file": True,
                "save_plugin_log_sqlite": True,
                "save_plugin_log_transit": True,
                "plugin_log_in_preview": True,
                "save_output_as_transit": True,
                "plugin_log_transit_name": "日志表",
                "transit_name": "结果表",
            },
            context={},
        )

        self.assertEqual(headers, ["B"])
        self.assertEqual(rows, [["b"]])
        self.assertIn("日志文件：plugin.log", stat)
        self.assertIn("SQLite日志：2条", stat)
        self.assertIn("中转副表：日志表", stat)
        self.assertIn("中转副表：结果表", stat)
        self.assertEqual([call[0] for call in transit_calls], ["日志表", "结果表"])

    def test_dataflowkit_apply_plugin_node_stop_policy_saves_logs_before_reraising(self):
        module = types.SimpleNamespace(run=lambda input_data, params, context: (_ for _ in ()).throw(RuntimeError("boom")))
        window = self.make_plugin_window(module)
        calls = []
        window.save_plugin_logs_to_file = lambda plugin_id, log_items: calls.append(("file", plugin_id, log_items)) or "plugin.log"
        window.save_plugin_logs_to_sqlite = lambda log_items, db_path=None, context=None: calls.append(("sqlite", db_path, log_items)) or 1
        window.save_plugin_output_to_transit = lambda *args, **kwargs: calls.append(("transit", args, kwargs)) or "中转副表：日志表"

        with self.assertRaisesRegex(RuntimeError, "boom"):
            window.apply_plugin_node(
                ["A"],
                [["a"]],
                {
                    "plugin_id": "test_plugin",
                    "params": {},
                    "plugin_failure_policy": "停止工作流",
                    "save_plugin_log_file": True,
                    "save_plugin_log_sqlite": True,
                    "save_plugin_log_transit": True,
                    "plugin_log_in_preview": True,
                },
                context={},
            )

        self.assertEqual([call[0] for call in calls], ["file", "sqlite"])
        self.assertEqual(calls[0][1], "test_plugin")
        self.assertIn("boom", calls[0][2][0]["message"])

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
