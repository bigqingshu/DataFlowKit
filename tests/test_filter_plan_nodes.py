# -*- coding: utf-8 -*-
import unittest

from workflow.nodes.filter_plan_nodes import (
    build_filter_config_probe_result,
    build_filter_runtime_plan,
    choose_plan_filter_lookup_fields,
    collect_plan_filter_required_fields,
    get_plan_filter_config_warnings,
    get_plan_filter_output_header_conflicts,
    get_plan_filter_output_headers,
    get_required_columns_for_plan_table,
    make_current_table_records,
    normalize_plan_filter_config_field_references,
)


class FilterPlanNodesTests(unittest.TestCase):
    def test_normalize_refs_and_output_headers(self):
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
                    "value": "当前表.当前表.普通文本",
                },
            ],
            "join_rules": [{"left": "当前表.当前表.编码", "op": "等于", "right": "allowed.a"}],
            "output_fields": ["当前表.当前表.编码", "allowed.a"],
        }

        normalize_plan_filter_config_field_references(config, ["编码", "对照编码"], ["allowed"])

        self.assertEqual(config["conditions"][0]["field"], "当前表.编码")
        self.assertEqual(config["conditions"][0]["value"], "当前表.对照编码")
        self.assertEqual(config["conditions"][1]["value"], "当前表.当前表.普通文本")
        self.assertEqual(config["join_rules"][0]["left"], "当前表.编码")
        self.assertEqual(config["output_fields"], ["当前表.编码", "allowed.a"])
        self.assertEqual(
            get_plan_filter_output_headers(["当前表.物料表.名称", "物料表.名称", "物料表.名称"], ["物料表.名称"]),
            ["物料表.名称", "物料表.名称_2", "物料表.名称_3"],
        )
        self.assertEqual(
            get_plan_filter_output_header_conflicts(
                ["当前表.物料表.名称", "物料表.名称", "物料表.名称"],
                ["物料表.名称"],
            ),
            ["物料表.名称"],
        )

    def test_required_fields_and_warnings(self):
        join_rules = [{"left": "当前表.A", "op": "等于", "right": "t.C"}]

        self.assertEqual(
            get_required_columns_for_plan_table("t", ["C", "Name", "Other"], {"t.C", "t.Name"}),
            ["C", "Name"],
        )
        current_required, table_required = collect_plan_filter_required_fields(
            ["A", "B"],
            ["t"],
            [{"field": "当前表.B", "op": "等于", "value_source": "字段值", "value": "t.Name"}],
            join_rules,
            ["当前表.A"],
            ["当前表.A", "t.Name"],
        )
        self.assertEqual(current_required, {"A", "B"})
        self.assertEqual(table_required, {"t": {"t.C", "t.Name"}})
        self.assertEqual(make_current_table_records(["A", "B"], [["x", "b"]], {"A"}), [{"A": "x", "当前表.A": "x"}])
        self.assertEqual(
            get_plan_filter_config_warnings(["A"], ["t"], [], [], "AND"),
            ["未设置筛选条件，副表会先按匹配规则读取全部可用行", "已选择副表但没有多表匹配规则，正式运行可能形成全组合"],
        )

    def test_runtime_plan_selects_fields_and_probe_result(self):
        self.assertEqual(choose_plan_filter_lookup_fields(["A"], [], [], available_fields=["ignored"]), ["A"])
        self.assertEqual(choose_plan_filter_lookup_fields(["A"], ["t"], [], available_fields=["当前表.A", "t.B"]), ["当前表.A", "t.B"])
        self.assertEqual(choose_plan_filter_lookup_fields(["A"], ["t"], ["t.B"], available_fields=["当前表.A"]), ["t.B"])

        plan = build_filter_runtime_plan(
            ["A", "B"],
            {
                "conditions": [{"field": "当前表.当前表.A", "op": "等于", "value_source": "字段值", "value": "当前表.当前表.B"}],
                "join_rules": [{"left": "当前表.当前表.A", "op": "等于", "right": "t.Code"}],
                "extra_tables": ["t"],
                "output_fields": [],
            },
            available_fields=["当前表.A", "t.Name"],
        )

        self.assertEqual(plan["runtime_config"]["conditions"][0]["field"], "当前表.A")
        self.assertEqual(plan["runtime_config"]["conditions"][0]["value"], "当前表.B")
        self.assertEqual(plan["lookup_fields"], ["当前表.A", "t.Name"])
        self.assertEqual(plan["output_headers"], ["A", "t.Name"])
        self.assertEqual(plan["current_required"], None)
        self.assertEqual(plan["table_required"], {"t": None})
        self.assertEqual(
            build_filter_config_probe_result(["A", "t.Name"]),
            (["A", "t.Name"], [], "配置探测：跳过高级筛选多表匹配，仅返回字段结构 2 列；正式预览/执行时会按规则计算。"),
        )


if __name__ == "__main__":
    unittest.main()
