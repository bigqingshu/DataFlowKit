# -*- coding: utf-8 -*-
import unittest

from workflow.filter_config_helpers import (
    build_filter_actual_output_text,
    build_filter_condition_input_state,
    build_filter_field_refresh_state,
    build_filter_field_refresh_status,
    build_filter_join_input_state,
    build_filter_risk_display_state,
    build_filter_selectable_tables,
    build_treeview_cell_edit_state,
    choose_filter_actual_output_lookup_fields,
    append_filter_condition_row,
    append_filter_join_rule_row,
    delete_filter_rows_by_indexes,
    ensure_filter_config_defaults,
    apply_treeview_cell_edit,
    filter_condition_from_row,
    filter_conditions_from_rows,
    filter_conditions_to_rows,
    filter_join_rule_from_row,
    filter_join_rules_from_rows,
    filter_join_rules_to_rows,
    filter_dedupe_button_text,
    invert_filter_output_fields,
    invert_filter_output_fields_by_indexes,
    normalize_treeview_row_values,
    parse_treeview_column_index,
    select_all_filter_output_fields,
    select_current_table_filter_output_fields,
    toggle_filter_dedupe_config,
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

    def test_condition_row_actions_append_and_delete(self):
        rows = [("当前表.A", "包含", "固定值", "x")]

        rows = append_filter_condition_row(rows, "当前表.B", "等于", "字段", "t.B")

        self.assertEqual(
            rows,
            [
                ("当前表.A", "包含", "固定值", "x"),
                ("当前表.B", "等于", "字段值", "t.B"),
            ],
        )
        self.assertEqual(delete_filter_rows_by_indexes(rows, [0]), [("当前表.B", "等于", "字段值", "t.B")])
        self.assertEqual(delete_filter_rows_by_indexes(rows, [2]), rows)

    def test_join_rules_round_trip(self):
        rows = filter_join_rules_to_rows([
            {"left": "当前表.A", "op": "等于", "right": "t.A"},
            {"left": "当前表.B", "right": "t.B"},
        ])

        self.assertEqual(rows, [("当前表.A", "等于", "t", "A"), ("当前表.B", "等于", "t", "B")])
        self.assertEqual(
            filter_join_rules_from_rows(rows),
            [
                {"left": "当前表.A", "op": "等于", "right_table": "t", "right": "t.A"},
                {"left": "当前表.B", "op": "等于", "right_table": "t", "right": "t.B"},
            ],
        )
        self.assertEqual(filter_join_rule_from_row(("L",)), {"left": "L", "op": "", "right": ""})

    def test_join_rule_row_actions_append_and_delete(self):
        rows = [("当前表.A", "等于", "t", "A")]

        rows = append_filter_join_rule_row(rows, "当前表.B", "", "t.B")

        self.assertEqual(rows, [("当前表.A", "等于", "t", "A"), ("当前表.B", "", "t", "B")])
        self.assertEqual(delete_filter_rows_by_indexes(rows, [1, 0]), [])

    def test_treeview_cell_edit_helpers(self):
        self.assertEqual(parse_treeview_column_index("#1", 4), 0)
        self.assertEqual(parse_treeview_column_index("#4", 4), 3)
        self.assertIsNone(parse_treeview_column_index("#5", 4))
        self.assertIsNone(parse_treeview_column_index("bad", 4))
        self.assertEqual(normalize_treeview_row_values(("A",), 3), ["A", "", ""])

        state = build_treeview_cell_edit_state(("A", "包含"), "#3", 4)
        self.assertEqual(state["column_index"], 2)
        self.assertEqual(state["values"], ["A", "包含", "", ""])
        self.assertEqual(state["text"], "")
        self.assertIsNone(build_treeview_cell_edit_state(("A",), "#0", 4))
        self.assertEqual(
            apply_treeview_cell_edit(("A", "包含"), 2, "固定值", 4),
            ["A", "包含", "固定值", ""],
        )
        self.assertIsNone(apply_treeview_cell_edit(("A",), 4, "x", 4))

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

    def test_condition_and_join_input_states(self):
        fields = ["当前表.A", "当前表.B", "t.Code"]

        state = build_filter_condition_input_state(fields, value_source="字段", current_value="")

        self.assertEqual(state["field_default"], "当前表.A")
        self.assertEqual(state["value_source"], "字段值")
        self.assertEqual(state["value_choices"], fields)
        self.assertEqual(state["value_default"], "当前表.A")

        fixed_state = build_filter_condition_input_state(fields, value_source="固定值", current_value="manual")
        self.assertEqual(fixed_state["value_source"], "固定值")
        self.assertEqual(fixed_state["value_choices"], [])
        self.assertEqual(fixed_state["value_default"], "manual")

        join_state = build_filter_join_input_state(["当前表.A", "当前表.B"], fields)
        self.assertEqual(join_state["left_default"], "当前表.A")
        self.assertEqual(join_state["right_default"], "t.Code")

        fallback_join_state = build_filter_join_input_state([], ["当前表.A"])
        self.assertEqual(fallback_join_state["left_default"], "当前表.A")
        self.assertEqual(fallback_join_state["right_default"], "当前表.A")

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

    def test_dedupe_config_toggle_and_text(self):
        config = {}

        self.assertEqual(filter_dedupe_button_text(False), "去除重复内容:关")
        self.assertEqual(filter_dedupe_button_text(True), "去除重复内容:开")
        self.assertTrue(toggle_filter_dedupe_config(config))
        self.assertEqual(config["remove_duplicates"], True)
        self.assertFalse(toggle_filter_dedupe_config(config))
        self.assertEqual(config["remove_duplicates"], False)

    def test_risk_and_refresh_display_states(self):
        self.assertEqual(
            build_filter_risk_display_state([]),
            {
                "text": "状态：当前多表筛选未发现明显全组合风险。",
                "foreground": "gray",
            },
        )
        self.assertEqual(
            build_filter_risk_display_state(["缺少匹配", "可能全组合"]),
            {
                "text": "风险提示：缺少匹配；可能全组合",
                "foreground": "#9a5a00",
            },
        )
        self.assertEqual(
            build_filter_field_refresh_status(2, 7),
            "高级筛选字段已局部刷新：2 个副表，7 个可用字段。",
        )


if __name__ == "__main__":
    unittest.main()
