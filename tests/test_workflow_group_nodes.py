# -*- coding: utf-8 -*-
import unittest

from DataFlowKit import PlanWorkflowWindow
from workflow.nodes.group_nodes import (
    apply_group_mapping,
    apply_inferred_group_inputs,
    apply_group_template_config,
    auto_group_mapping_by_name,
    build_empty_group_stat,
    build_group_final_output,
    build_group_input_table,
    build_group_node_log,
    build_group_output_config_state,
    build_group_status_text,
    copy_group_inner_node,
    delete_group_inner_node,
    ensure_group_parent_context,
    ensure_group_config_defaults,
    group_input_fields_text,
    group_mapping_detail,
    group_mapping_rows,
    group_node_label,
    group_node_labels,
    group_selected_input_state,
    group_source_field_combo_state,
    group_source_headers_for_mapping,
    make_group_child_context,
    merge_group_child_audit_logs,
    move_group_inner_node,
    normalize_group_sqlite_mode,
    normalize_group_transit_conflict_mode,
    parse_group_inner_node_json,
    parse_group_input_fields,
    toggle_group_inner_node_enabled,
    unique_keep_order,
    update_group_input_fields_config,
    use_source_headers_as_group_inputs,
)


class WorkflowGroupNodesTests(unittest.TestCase):
    def test_parse_group_input_fields_dedupes_and_supports_text(self):
        self.assertEqual(unique_keep_order([" A ", "B", "A", "", " C "]), ["A", "B", "C"])
        self.assertEqual(parse_group_input_fields({"input_fields": "A, B；A\nC"}), ["A", "B", "C"])
        self.assertEqual(parse_group_input_fields({"input_fields": ["A", " B ", "A"]}), ["A", "B"])

    def test_group_config_ui_state_helpers(self):
        config = {
            "group_name": "G",
            "input_fields": ["A", "B"],
            "input_mapping": {"A": "srcA", "old": "srcOld"},
            "input_defaults": {"B": "b", "old": "old"},
        }

        ensure_group_config_defaults(config)
        fields = update_group_input_fields_config(config, "B, C, B")

        self.assertEqual(fields, ["B", "C"])
        self.assertEqual(group_input_fields_text(config), "B,C")
        self.assertEqual(config["input_mapping"], {})
        self.assertEqual(config["input_defaults"], {"B": "b"})
        self.assertEqual(group_mapping_rows(config), [("B", "", "b"), ("C", "", "")])
        self.assertEqual(group_mapping_detail(config, "B"), {"source_field": "", "default_value": "b"})
        self.assertEqual(group_selected_input_state(config, "missing"), {"values": ["B", "C"], "value": "B"})
        self.assertEqual(
            group_source_headers_for_mapping("中转副表", ["cur"], {"tmp": {"headers": ["T1"]}}, "tmp"),
            ["T1"],
        )
        self.assertEqual(group_source_headers_for_mapping("SQLite表", ["cur"], sqlite_columns=["S1"]), ["S1"])
        self.assertEqual(group_source_field_combo_state("missing", ["S1"]), {"values": ["", "S1"], "value": ""})

    def test_group_output_config_state(self):
        state = build_group_output_config_state({
            "group_name": "G",
            "save_to_transit": True,
            "save_to_sqlite": False,
        })

        self.assertEqual(state["main_output_mode"], "输出为当前工作表")
        self.assertEqual(state["main_output_choices"], ["输出为当前工作表", "透传原当前表"])
        self.assertEqual(state["transit_scope_choices"], ["组内中转私有", "允许输出到外部"])
        self.assertTrue(state["save_to_transit"])
        self.assertEqual(state["output_transit_name"], "G")
        self.assertFalse(state["save_to_sqlite"])
        self.assertEqual(state["output_sqlite_table"], "G")
        self.assertIn("SQLite 默认只在【执行计划】时保存", state["hint_text"])

    def test_group_mapping_actions(self):
        config = {"input_fields": ["Name", "Code"], "input_mapping": {}, "input_defaults": {}}

        self.assertEqual(apply_group_mapping(config, "", "A", ""), {"ok": False, "message": "请先在组入口字段下拉框中选择一个入口字段。"})
        self.assertFalse(apply_group_mapping(config, "Missing", "A", "")["ok"])
        self.assertEqual(apply_group_mapping(config, "Name", "姓名", "无名"), {"ok": True, "message": ""})
        self.assertEqual(config["input_mapping"]["Name"], "姓名")
        self.assertEqual(config["input_defaults"]["Name"], "无名")

        auto_group_mapping_by_name(config, ["name", "Code"])
        self.assertEqual(config["input_mapping"]["Code"], "Code")
        self.assertEqual(config["input_mapping"]["Name"], "姓名")

        fields = use_source_headers_as_group_inputs(config, ["A", "B"])
        self.assertEqual(fields, ["A", "B"])
        self.assertEqual(config["input_mapping"], {"A": "A", "B": "B"})

        config = {"input_fields": ["A"], "input_mapping": {"A": "OldA"}, "input_defaults": {"A": "a"}}
        new_fields = apply_inferred_group_inputs(config, ["B", "C"], ["b", "C"], merge=True)
        self.assertEqual(new_fields, ["A", "B", "C"])
        self.assertEqual(config["input_mapping"], {"A": "OldA", "B": "b", "C": "C"})
        self.assertEqual(config["input_defaults"], {"A": "a", "B": "", "C": ""})

    def test_group_inner_node_list_actions(self):
        nodes = [
            {"type": "A", "name": "one", "enabled": True},
            {"type": "B", "name": "two", "enabled": False},
        ]

        self.assertEqual(group_node_label(0, nodes[0]), "01. [✓] A - one")
        self.assertEqual(group_node_labels(nodes), ["01. [✓] A - one", "02. [×] B - two"])

        moved, index = move_group_inner_node(nodes, 0, 1)
        self.assertEqual([node["type"] for node in moved], ["B", "A"])
        self.assertEqual(index, 1)

        copied, index = copy_group_inner_node(nodes, 0)
        self.assertEqual(copied[1]["name"], "one_复制")
        self.assertEqual(index, 1)
        copied[1]["name"] = "changed"
        self.assertEqual(nodes[0]["name"], "one")

        toggled, index = toggle_group_inner_node_enabled(nodes, 1)
        self.assertTrue(toggled[1]["enabled"])
        self.assertEqual(index, 1)

        deleted, index = delete_group_inner_node(nodes, 0)
        self.assertEqual([node["type"] for node in deleted], ["B"])
        self.assertEqual(index, 0)

    def test_group_inner_node_json_and_template_helpers(self):
        self.assertEqual(parse_group_inner_node_json('{"type":"新建列","config":{}}')["type"], "新建列")
        with self.assertRaisesRegex(ValueError, "必须是包含 type"):
            parse_group_inner_node_json('{"config":{}}')
        with self.assertRaisesRegex(ValueError, "不支持组内循环节点"):
            parse_group_inner_node_json('{"type":"循环执行起点"}')
        with self.assertRaises(ValueError):
            parse_group_inner_node_json("{bad")

        config = {"old": 1}
        apply_group_template_config(config, {"group_name": "G", "nodes": []})
        self.assertEqual(config, {"group_name": "G", "nodes": []})
        with self.assertRaisesRegex(ValueError, "必须是对象"):
            apply_group_template_config(config, None)

    def test_build_group_input_table_maps_fields_and_defaults(self):
        headers, rows, stat = build_group_input_table(
            ["姓名", "年龄"],
            [["张三", "18"], ["李四"]],
            {
                "input_fields": ["name", "age", "city"],
                "input_mapping": {"name": "姓名", "age": "年龄"},
                "input_defaults": {"city": "广州"},
            },
        )

        self.assertEqual(headers, ["name", "age", "city"])
        self.assertEqual(rows, [["张三", "18", "广州"], ["李四", "", "广州"]])
        self.assertEqual(stat, "入口字段映射 3 列")

    def test_build_group_input_table_raises_on_missing_mapping_when_configured(self):
        with self.assertRaisesRegex(ValueError, "节点组入口映射缺失字段：city"):
            build_group_input_table(
                ["姓名"],
                [["张三"]],
                {
                    "input_fields": ["name", "city"],
                    "input_mapping": {"name": "姓名"},
                    "missing_input_policy": "缺失报错",
                },
            )

    def test_build_group_input_table_passes_through_when_no_input_fields(self):
        self.assertEqual(
            build_group_input_table(["A"], [["a"]], {"input_fields": []}),
            (["A"], [["a"]], "入口字段未设置，使用来源整表"),
        )

    def test_make_group_child_context_isolates_transit_by_default(self):
        parent = {
            "transit_tables": {"T": {"headers": ["A"], "rows": [["a"]]}},
            "loop_states": {"x": 1},
            "loop_results": {"y": 2},
            "table_access_policy": {"mode": "test"},
        }

        child = make_group_child_context(parent, {"group_name": "G"})

        self.assertIsNot(child, parent)
        self.assertEqual(child["group_name"], "G")
        self.assertEqual(child["table_access_policy"], {"mode": "test"})
        child["transit_tables"]["T"]["rows"][0][0] = "changed"
        self.assertEqual(parent["transit_tables"]["T"]["rows"], [["a"]])

    def test_make_group_child_context_can_share_parent_when_enabled(self):
        parent = ensure_group_parent_context({})

        child = make_group_child_context(parent, {"transit_scope": "允许输出到外部"})

        self.assertIs(child, parent)
        self.assertIn("transit_tables", parent)
        self.assertIn("loop_states", parent)
        self.assertIn("loop_results", parent)

    def test_merge_group_child_audit_logs_moves_child_logs(self):
        parent = {}
        child = {"table_access_logs": [{"action": "read"}]}

        merge_group_child_audit_logs(parent, child)

        self.assertEqual(parent["table_access_logs"], [{"action": "read"}])
        self.assertEqual(child["table_access_logs"], [])

    def test_group_output_modes_and_status_text(self):
        self.assertEqual(normalize_group_transit_conflict_mode("追加到原表"), "追加")
        self.assertEqual(normalize_group_transit_conflict_mode("自动加时间戳新表"), "自动加时间戳")
        self.assertEqual(normalize_group_transit_conflict_mode("覆盖整表"), "覆盖")
        self.assertEqual(normalize_group_sqlite_mode("追加"), "append")
        self.assertEqual(normalize_group_sqlite_mode("覆盖"), "replace")
        self.assertEqual(normalize_group_sqlite_mode("存在则报错"), "fail")
        self.assertEqual(normalize_group_sqlite_mode("新表"), "timestamp")

        self.assertEqual(
            build_group_final_output(["A"], [["a"]], ["B"], [["b"]], {"main_output_mode": "透传原当前表"}),
            (["A"], [["a"]], "主输出=透传原当前表"),
        )
        self.assertEqual(
            build_group_final_output(["A"], [["a"]], ["B"], [["b"]], {}),
            (["B"], [["b"]], "主输出=组结果作为当前表"),
        )

        self.assertEqual(build_group_node_log(1, "新建列", (2, 1), (2, 2), "OK"), "1.新建列 2×1→2×2 OK")
        self.assertIn("节点组【G】为空，输出入口表", build_empty_group_stat("G", "当前工作表", "入口", ["中转副表：T"]))
        stat = build_group_status_text("G", "当前工作表", "入口", "主输出=组结果作为当前表", logs=["1.A", "2.B"], output_parts=["SQLite表：T"])
        self.assertIn("节点组【G】完成：来源=当前工作表", stat)
        self.assertIn("SQLite表：T", stat)
        self.assertIn("1.A；2.B", stat)

    def test_dataflowkit_run_group_inner_nodes_prepares_permissions_and_logs_shape(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        calls = []
        window.ensure_node_identity = lambda node: node.setdefault("node_id", "generated")
        window.refresh_node_table_access = lambda node: node.setdefault("table_access", {"current_table": {}})

        def fake_check(context, headers, write=False, operation=""):
            calls.append(("check", operation, write, list(headers), context.get("current_node_info", {}).get("node_type")))
            return {"operation": operation, "write": write}

        def fake_apply(headers, rows, node, execute_actions=False, context=None):
            calls.append(("apply", node.get("type"), context.get("current_node_info", {}).get("node_index")))
            return list(headers) + ["B"], [list(row) + ["b"] for row in rows], "done"

        def fake_log(manager, before_shape, headers, rows, node_type=None):
            calls.append(("log", node_type, before_shape, (len(rows), len(headers)), manager.get("operation")))

        window.check_current_table_permission = fake_check
        window.get_table_manager = lambda context, node_type="": {"operation": "jump", "write": False}
        window.apply_node = fake_apply
        window.log_current_table_transform = fake_log

        child_context = {}
        headers, rows, logs = window.run_group_inner_nodes(
            ["A"],
            [["a"]],
            [
                {"type": "新建列", "name": "n1", "config": {}},
                {"type": "删除行", "enabled": False, "config": {}},
            ],
            child_context,
            execute_actions=True,
        )

        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["a", "b"]])
        self.assertEqual(logs, ["1.新建列 1×1→1×2 done", "2.删除行 已禁用"])
        self.assertEqual(child_context["current_node_info"]["node_index"], 0)
        self.assertIn(("check", "read_current_table", False, ["A"], "新建列"), calls)
        self.assertIn(("check", "write_current_table", True, ["A"], "新建列"), calls)
        self.assertIn(("apply", "新建列", 0), calls)
        self.assertIn(("log", "新建列", (1, 1), (1, 2), "write_current_table"), calls)

    def test_dataflowkit_group_config_source_headers_resolves_sources(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        window.get_workflow_sqlite_columns = lambda table, context=None: ["S1", "S2"] if table == "sql" else []
        context = {"transit_tables": {"tmp": {"headers": ["T1"]}}}

        self.assertEqual(
            window.get_group_config_source_headers("当前工作表", ["A"], context),
            ["A"],
        )
        self.assertEqual(
            window.get_group_config_source_headers("中转副表", ["A"], context, transit_name="tmp"),
            ["T1"],
        )
        self.assertEqual(
            window.get_group_config_source_headers("SQLite表", ["A"], context, sqlite_table="sql"),
            ["S1", "S2"],
        )

    def test_dataflowkit_group_json_and_template_methods(self):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        config = {"nodes": [{"type": "旧节点", "name": "old"}]}

        index = window.save_group_inner_node_json_text(config, 0, '{"type":"新建列","name":"new","config":{}}')

        self.assertEqual(index, 0)
        self.assertEqual(config["nodes"][0]["type"], "新建列")
        with self.assertRaisesRegex(ValueError, "请先选择"):
            window.save_group_inner_node_json_text(config, None, "{}")
        with self.assertRaisesRegex(ValueError, "不支持组内循环节点"):
            window.save_group_inner_node_json_text(config, 0, '{"type":"循环判断回跳"}')

        calls = []
        window.load_group_template_dialog = lambda: {"template": True}
        window.group_config_from_template_data = lambda data: {"group_name": "G", "nodes": []}
        window.rebuild_current_config = lambda: calls.append("rebuild")
        target = {"old": 1}

        self.assertTrue(window.load_group_template_into_config(target))
        self.assertEqual(target, {"group_name": "G", "nodes": []})
        self.assertEqual(calls, ["rebuild"])

        window.load_group_template_dialog = lambda: None
        self.assertFalse(window.load_group_template_into_config(target))
        self.assertEqual(calls, ["rebuild"])


if __name__ == "__main__":
    unittest.main()
