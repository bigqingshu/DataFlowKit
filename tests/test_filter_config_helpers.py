# -*- coding: utf-8 -*-
import unittest

from workflow.filter_config_helpers import (
    build_filter_actual_output_text,
    build_filter_field_refresh_state,
    build_filter_selectable_tables,
    choose_filter_actual_output_lookup_fields,
    ensure_filter_config_defaults,
    filter_condition_from_row,
    filter_conditions_from_rows,
    filter_conditions_to_rows,
    filter_join_rule_from_row,
    filter_join_rules_from_rows,
    filter_join_rules_to_rows,
    invert_filter_output_fields,
    invert_filter_output_fields_by_indexes,
    select_all_filter_output_fields,
    select_current_table_filter_output_fields,
)


class FilterConfigHelpersTests(unittest.TestCase):
    def test_defaults_and_selectable_tables(self):
        config = {}

        ensure_filter_config_defaults(config)

        self.assertEqual(config["logic"], "AND")
        self.assertEqual(config["join_logic"], "AND")
        self.assertEqual(config["conditions"], [])
        self.assertEqual(config["join_rules"], [])
        self.assertEqual(config["extra_tables"], [])
        self.assertEqual(config["output_fields"], [])
        self.assertEqual(config["result_limit"], "5000")
        self.assertEqual(config["max_intermediate"], "200000")
        self.assertFalse(config["remove_duplicates"])
        self.assertEqual(
            build_filter_selectable_tables(["sqlite_a"], ["z", "a"]),
            ["sqlite_a", "中转:a", "中转:z"],
        )

    def test_conditions_round_trip_normalizes_value_source(self):
        rows = filter_conditions_to_rows([
            {"field": "当前表.A", "op": "等于", "value_source": "字段", "value": "t.B"},
            {"field": "当前表.C", "op": "包含", "value": "fixed"},
        ])

        self.assertEqual(rows[0], ("当前表.A", "等于", "字段值", "t.B"))
        self.assertEqual(rows[1], ("当前表.C", "包含", "固定值", "fixed"))
        self.assertEqual(
            filter_conditions_from_rows(rows),
            [
                {"field": "当前表.A", "op": "等于", "value_source": "字段值", "value": "t.B"},
                {"field": "当前表.C", "op": "包含", "value_source": "固定值", "value": "fixed"},
            ],
        )
        self.assertEqual(
            filter_condition_from_row(("当前表.A", "等于")),
            {"field": "当前表.A", "op": "等于", "value_source": "固定值", "value": ""},
        )

    def test_join_rules_round_trip(self):
        rows = filter_join_rules_to_rows([
            {"left": "当前表.A", "op": "等于", "right": "t.A"},
            {"left": "当前表.B", "right": "t.B"},
        ])

        self.assertEqual(rows, [("当前表.A", "等于", "t.A"), ("当前表.B", "等于", "t.B")])
        self.assertEqual(
            filter_join_rules_from_rows(rows),
            [
                {"left": "当前表.A", "op": "等于", "right": "t.A"},
                {"left": "当前表.B", "op": "等于", "right": "t.B"},
            ],
        )
        self.assertEqual(filter_join_rule_from_row(("L",)), {"left": "L", "op": "", "right": ""})

    def test_output_field_choices_and_actual_text(self):
        all_fields = ["当前表.A", "当前表.B", "t.A"]

        self.assertEqual(
            choose_filter_actual_output_lookup_fields([], ["A", "B"], all_fields, []),
            ["A", "B"],
        )
        self.assertEqual(
            choose_filter_actual_output_lookup_fields([], ["A", "B"], all_fields, ["t"]),
            all_fields,
        )
        self.assertEqual(
            choose_filter_actual_output_lookup_fields(["t.A"], ["A", "B"], all_fields, ["t"]),
            ["t.A"],
        )
        self.assertEqual(select_all_filter_output_fields(all_fields), all_fields)
        self.assertEqual(invert_filter_output_fields(all_fields, ["当前表.B"]), ["当前表.A", "t.A"])
        self.assertEqual(invert_filter_output_fields_by_indexes(["A", "A", "B"], [1]), ["A", "B"])
        self.assertEqual(select_current_table_filter_output_fields(all_fields), ["当前表.A", "当前表.B"])
        self.assertEqual(
            build_filter_actual_output_text(["当前表.A", "t.A"], ["A"], all_fields, ["t"]),
            "实际输出字段：A、t.A",
        )
        self.assertIn(
            "重名自动编号：A",
            build_filter_actual_output_text(["当前表.A", "A"], ["A"], all_fields, []),
        )

    def test_field_refresh_state_calculates_combo_fallbacks(self):
        state = build_filter_field_refresh_state(
            ["A", "B"],
            ["当前表.A", "当前表.B", "t.Code"],
            value_source="字段",
            selected_output_fields=["当前表.B"],
        )

        self.assertEqual(state["current_values"], ["当前表.A", "当前表.B"])
        self.assertEqual(state["first_any"], "当前表.A")
        self.assertEqual(state["first_current"], "当前表.A")
        self.assertEqual(state["first_external"], "t.Code")
        self.assertEqual(state["value_choices"], ["当前表.A", "当前表.B", "t.Code"])
        self.assertEqual(state["value_fallback"], "当前表.A")
        self.assertEqual(state["selected_output"], {"当前表.B"})
        self.assertEqual(state["value_source"], "字段值")

        fixed_state = build_filter_field_refresh_state(["A"], ["当前表.A"], value_source="固定值")
        self.assertEqual(fixed_state["value_choices"], [])
        self.assertEqual(fixed_state["value_fallback"], "")
        self.assertEqual(fixed_state["first_external"], "当前表.A")

        empty_state = build_filter_field_refresh_state([], [], value_source="字段值")
        self.assertEqual(empty_state["first_any"], "")
        self.assertEqual(empty_state["first_current"], "")
        self.assertEqual(empty_state["first_external"], "")
        self.assertEqual(empty_state["value_choices"], [])


if __name__ == "__main__":
    unittest.main()
