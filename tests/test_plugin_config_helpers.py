# -*- coding: utf-8 -*-
import unittest

from workflow.plugin_config_helpers import (
    apply_plugin_custom_config_result,
    build_plugin_dynamic_control_state,
    build_plugin_dynamic_select_choices,
    build_plugin_field_select_initial_value,
    build_plugin_input_spec,
    build_plugin_input_table_choices,
    build_plugin_load_status_state,
    build_plugin_select_initial_value,
    default_plugin_input_spec,
    ensure_plugin_input_specs,
    format_plugin_input_spec,
    get_plugin_field_choices_for_table_param,
    get_plugin_input_table_alias_choices,
    get_plugin_static_parameter_choices,
    normalize_plugin_run_mode,
    normalize_plugin_dynamic_parameter_choices,
    plugin_config_transit_reuse_note,
    plugin_input_spec_to_rows,
    resolve_plugin_field_table_alias,
    with_current_value_in_choices,
)


class PluginConfigHelpersTests(unittest.TestCase):
    def test_run_mode_and_load_status_state(self):
        self.assertEqual(normalize_plugin_run_mode("external_python", ["主程序内置环境", "插件独立环境"]), "插件独立环境")
        self.assertEqual(normalize_plugin_run_mode("主程序内置环境", ["插件独立环境"]), "插件独立环境")
        self.assertEqual(normalize_plugin_run_mode("", []), "主程序内置环境")

        state = build_plugin_load_status_state("仅独立环境运行", "manifest", "missing dep")
        self.assertIn("加载状态：仅独立环境运行", state["text"])
        self.assertIn("元信息来源：manifest", state["text"])
        self.assertEqual(state["foreground"], "#b26a00")
        self.assertEqual(state["import_error_text"], "主程序环境导入提示：missing dep")

        ok_state = build_plugin_load_status_state("可内置运行")
        self.assertEqual(ok_state["foreground"], "gray")
        self.assertEqual(ok_state["import_error_text"], "")

    def test_input_spec_defaults_format_and_rows(self):
        config = {"input_tables": "bad"}

        specs = ensure_plugin_input_specs(config)

        self.assertEqual(specs, [])
        self.assertIs(config["input_tables"], specs)
        self.assertEqual(
            default_plugin_input_spec(1, ["sqlite_a"], ["transit_a"]),
            {
                "alias": "输入表2",
                "source_type": "SQLite表",
                "sqlite_table": "sqlite_a",
                "transit_table": "transit_a",
                "enabled": True,
            },
        )
        self.assertEqual(format_plugin_input_spec({"alias": "A", "source_type": "SQLite表", "sqlite_table": "orders"}), "A <- SQLite表:orders")
        self.assertEqual(format_plugin_input_spec({"source_type": "中转副表", "transit_table": "tmp", "enabled": False}), "输入表 <- 中转副表:tmp [停用]")
        self.assertEqual(format_plugin_input_spec({"source_type": "当前工作流表"}), "输入表 <- 当前工作流表:当前工作流表")
        self.assertEqual(
            plugin_input_spec_to_rows([{"alias": "A", "source_type": "SQLite表", "table": "legacy"}, "bad"]),
            ["A <- SQLite表:legacy"],
        )
        self.assertEqual(
            build_plugin_input_spec("", "", " t ", " m ", False, fallback_index=2),
            {
                "alias": "输入表3",
                "source_type": "SQLite表",
                "sqlite_table": "t",
                "transit_table": "m",
                "enabled": False,
            },
        )
        self.assertEqual(
            build_plugin_input_table_choices(["sqlite_b", "sqlite_a"], {"transit_tables": {"tmp_b": {}, "tmp_a": {}}}),
            {"sqlite_tables": ["sqlite_b", "sqlite_a"], "transit_names": ["tmp_a", "tmp_b"]},
        )

    def test_transit_reuse_note_limits_names(self):
        self.assertEqual(plugin_config_transit_reuse_note({}), "")
        self.assertEqual(
            plugin_config_transit_reuse_note({"_reused_preview_transit_tables": ["a", "b", "c", "d", "e", "f"]}),
            "插件设置窗口将复用上次真实预览/执行生成的中转副表数据：a、b、c、d、e 等 6 个",
        )

    def test_alias_and_field_choice_helpers(self):
        table_headers = {
            "当前表": ["A"],
            "workflow_current": ["A"],
            "primary": ["A"],
            "明细": ["B"],
            "停用": ["C"],
            "其他": ["D"],
        }
        specs = [
            {"alias": "明细", "enabled": True},
            {"alias": "停用", "enabled": False},
        ]

        self.assertEqual(
            get_plugin_input_table_alias_choices(table_headers, specs),
            ["当前表", "明细", "workflow_current", "primary", "停用", "其他"],
        )

        spec = {"table_param": "source", "default_table_alias": "明细"}
        self.assertEqual(resolve_plugin_field_table_alias(spec, {"source": "其他"}), "其他")
        self.assertEqual(get_plugin_field_choices_for_table_param(spec, {"source": "明细"}, table_headers), ["B"])
        self.assertEqual(resolve_plugin_field_table_alias({"table_alias": "明细"}, {}), "明细")
        self.assertEqual(resolve_plugin_field_table_alias({}, {}), "当前表")

    def test_initial_value_and_choice_helpers(self):
        self.assertEqual(with_current_value_in_choices("x", ["a", "b"]), ["x", "a", "b"])
        self.assertEqual(with_current_value_in_choices("a", ["a", "b"]), ["a", "b"])
        self.assertEqual(get_plugin_static_parameter_choices({"options": ["a"]}), ["a"])
        self.assertEqual(get_plugin_static_parameter_choices({"choices": ["c"]}), ["c"])
        self.assertEqual(normalize_plugin_dynamic_parameter_choices(["fallback"], {"choices": [1, "2"]}), ["1", "2"])
        self.assertEqual(normalize_plugin_dynamic_parameter_choices(["fallback"], {"options": ["x"]}), ["x"])
        self.assertEqual(normalize_plugin_dynamic_parameter_choices(["fallback"], "bad"), ["fallback"])
        self.assertEqual(build_plugin_select_initial_value("", ["a"], fallback="f"), "a")
        self.assertEqual(build_plugin_select_initial_value("", [], fallback="f"), "f")
        self.assertEqual(build_plugin_field_select_initial_value("", ["a"], default_value="b"), "a")
        self.assertEqual(build_plugin_field_select_initial_value("", ["a"], default_value="a"), "a")
        self.assertEqual(build_plugin_field_select_initial_value("", [], default_value="d"), "d")
        self.assertEqual(build_plugin_dynamic_select_choices({"allow_custom": True}, "old", ["new"]), ["old", "new"])

    def test_dynamic_control_state_fallbacks(self):
        self.assertEqual(
            build_plugin_dynamic_control_state("input_table_select", {}, "missing", ["当前表", "明细"]),
            {"choices": ["当前表", "明细"], "value": "当前表"},
        )
        self.assertEqual(
            build_plugin_dynamic_control_state("input_table_select", {}, "", []),
            {"choices": [], "value": "当前表"},
        )
        self.assertEqual(
            build_plugin_dynamic_control_state("input_table_field_select", {"default": "B"}, "", ["A", "B"]),
            {"choices": ["A", "B"], "value": "B"},
        )
        self.assertEqual(
            build_plugin_dynamic_control_state("input_table_field_select", {"allow_custom": True}, "Old", ["A"]),
            {"choices": ["Old", "A"], "value": "Old"},
        )
        self.assertEqual(
            build_plugin_dynamic_control_state("dynamic_select", {"allow_custom": False, "default": "D"}, "Old", ["A"]),
            {"choices": ["A"], "value": "A"},
        )
        self.assertEqual(
            build_plugin_dynamic_control_state("dynamic_select", {"default": "D"}, "", []),
            {"choices": [], "value": "D"},
        )

    def test_apply_plugin_custom_config_result(self):
        config = {"params": {"old": "value"}}
        params = config["params"]

        self.assertTrue(apply_plugin_custom_config_result(config, params, {"new": "value"}))

        self.assertEqual(params, {"new": "value"})
        self.assertIs(config["params"], params)
        self.assertFalse(apply_plugin_custom_config_result(config, params, None))


if __name__ == "__main__":
    unittest.main()
