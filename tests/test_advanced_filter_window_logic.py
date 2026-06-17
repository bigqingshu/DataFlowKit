# -*- coding: utf-8 -*-
import sqlite3
import tempfile
import unittest
from pathlib import Path

from workflow.advanced_filter_window_logic import (
    add_advanced_filter_output_fields,
    add_all_advanced_filter_output_fields,
    build_advanced_filter_field_display_cache,
    build_advanced_filter_template_data,
    build_advanced_filter_result_records,
    eval_advanced_filter_condition,
    eval_advanced_filter_conditions,
    eval_advanced_filter_join_rule,
    eval_advanced_filter_join_rules,
    filter_advanced_filter_valid_state,
    load_advanced_filter_table_records,
    normalize_advanced_filter_template_data,
    parse_advanced_filter_number,
    parse_positive_int_setting,
    remove_advanced_filter_output_fields,
    select_advanced_filter_combo_defaults,
    select_advanced_filter_template_tables,
)


class AdvancedFilterWindowLogicTests(unittest.TestCase):
    def test_parse_number_and_positive_int_setting(self):
        self.assertEqual(parse_advanced_filter_number("1,234.5"), 1234.5)
        self.assertIsNone(parse_advanced_filter_number(""))
        self.assertEqual(parse_positive_int_setting("10", 5), 10)
        self.assertEqual(parse_positive_int_setting("0", 5), 5)
        self.assertEqual(parse_positive_int_setting("bad", 5), 5)

    def test_eval_condition_supports_text_and_number_rules(self):
        record = {"t.A": "Alpha", "t.N": "12"}

        self.assertTrue(eval_advanced_filter_condition(record, {"field": "t.A", "op": "包含", "value": "ph"}))
        self.assertTrue(eval_advanced_filter_condition(record, {"field": "t.A", "op": "忽略大小写等于", "value": "alpha"}))
        self.assertTrue(eval_advanced_filter_condition(record, {"field": "t.N", "op": "大于", "value": "10"}))
        self.assertFalse(eval_advanced_filter_condition(record, {"field": "t.N", "op": "小于", "value": ""}))
        self.assertTrue(eval_advanced_filter_conditions(record, [{"field": "t.A", "op": "等于", "value": "x"}, {"field": "t.N", "op": "等于", "value": "12"}], "OR"))

    def test_eval_join_rules_preserves_deferred_and_empty_contains_behavior(self):
        record = {"a.Code": "ABC", "b.Code": "B"}

        self.assertTrue(eval_advanced_filter_join_rule(record, {"left": "a.Code", "op": "左包含右", "right": "b.Code"}))
        self.assertFalse(eval_advanced_filter_join_rule({"a.Code": "", "b.Code": "B"}, {"left": "a.Code", "op": "右包含左", "right": "b.Code"}))
        self.assertTrue(eval_advanced_filter_join_rules(record, [{"left": "missing", "op": "等于", "right": "b.Code"}], "AND"))
        self.assertFalse(eval_advanced_filter_join_rules(record, [{"left": "a.Code", "op": "等于", "right": "b.Code"}], "AND"))

    def test_load_table_records_prefixes_columns(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            db_path = str(Path(tmp) / "data.db")
            conn = sqlite3.connect(db_path)
            try:
                conn.execute('CREATE TABLE "people" ("id" TEXT, "name" TEXT)')
                conn.execute('INSERT INTO "people" VALUES (?, ?)', ("1", "Alice"))
                conn.execute('INSERT INTO "people" ("id") VALUES (?)', ("2",))
                conn.commit()
            finally:
                conn.close()

            records = load_advanced_filter_table_records(db_path, "people", ["id", "name", "missing"])

        self.assertEqual(
            records,
            [
                {"people.id": "1", "people.name": "Alice", "people.missing": ""},
                {"people.id": "2", "people.name": "", "people.missing": ""},
            ],
        )

    def test_build_result_records_filters_single_table_and_limits(self):
        records = build_advanced_filter_result_records(
            ["people"],
            {
                "people": [
                    {"people.name": "Alice", "people.age": "20"},
                    {"people.name": "Bob", "people.age": "30"},
                    {"people.name": "Cathy", "people.age": "40"},
                ]
            },
            conditions=[{"field": "people.age", "op": "大于等于", "value": "30"}],
            result_limit=1,
        )

        self.assertEqual(records, [{"people.name": "Bob", "people.age": "30"}])

    def test_build_result_records_joins_tables_and_checks_intermediate_limit(self):
        joined = build_advanced_filter_result_records(
            ["orders", "people"],
            {
                "orders": [
                    {"orders.id": "1", "orders.person_id": "A"},
                    {"orders.id": "2", "orders.person_id": "B"},
                ],
                "people": [
                    {"people.id": "A", "people.name": "Alice"},
                    {"people.id": "C", "people.name": "Cathy"},
                ],
            },
            join_rules=[{"left": "orders.person_id", "op": "等于", "right": "people.id"}],
        )

        self.assertEqual(joined, [{"orders.id": "1", "orders.person_id": "A", "people.id": "A", "people.name": "Alice"}])

        with self.assertRaisesRegex(RuntimeError, "中间结果超过上限 1 行"):
            build_advanced_filter_result_records(
                ["a", "b"],
                {
                    "a": [{"a.x": "1"}, {"a.x": "2"}],
                    "b": [{"b.y": "1"}, {"b.y": "2"}],
                },
                max_intermediate=1,
            )

    def test_template_helpers_export_and_filter_invalid_fields(self):
        data = build_advanced_filter_template_data(
            "main",
            ["main", "missing_table"],
            [{"field": "main.A", "op": "等于", "value": "x"}, {"field": "bad", "op": "等于", "value": "y"}],
            "OR",
            "AND",
            [{"left": "main.A", "op": "等于", "right": "other.A"}, {"left": "main.A", "op": "等于", "right": "bad"}],
            ["main.A", "bad"],
            "100",
            "200",
            "out",
        )

        self.assertEqual(data["selected_tables"], ["main", "missing_table"])
        normalized = normalize_advanced_filter_template_data(
            data,
            tables_cache=["main", "other"],
            valid_fields=["main.A", "other.A"],
            current_save_table="fallback",
        )

        self.assertEqual(normalized["selected_tables"], ["main"])
        self.assertEqual(normalized["conditions"], [{"field": "main.A", "op": "等于", "value": "x"}])
        self.assertEqual(normalized["join_rules"], [{"left": "main.A", "op": "等于", "right": "other.A"}])
        self.assertEqual(normalized["output_fields"], ["main.A"])
        self.assertEqual(normalized["save_table"], "out")
        self.assertEqual(
            select_advanced_filter_template_tables({"main_table": "other", "selected_tables": ["missing"]}, ["main", "other"]),
            ["other"],
        )

    def test_field_state_helpers_build_defaults_and_filter_invalid_items(self):
        fields = build_advanced_filter_field_display_cache(
            ["orders", "people", "missing"],
            {
                "orders": ["id", "person_id"],
                "people": ["id", "name"],
                "missing": None,
            },
        )
        self.assertEqual(fields, ["orders.id", "orders.person_id", "people.id", "people.name"])
        self.assertEqual(
            select_advanced_filter_combo_defaults(
                fields,
                filter_field="people.name",
                join_left="bad",
                join_right="",
            ),
            {
                "filter_field": "people.name",
                "join_left": "orders.id",
                "join_right": "orders.person_id",
            },
        )
        self.assertEqual(
            select_advanced_filter_combo_defaults([], "old_filter", "old_left", "old_right"),
            {
                "filter_field": "old_filter",
                "join_left": "old_left",
                "join_right": "old_right",
            },
        )

        state = filter_advanced_filter_valid_state(
            [
                {"field": "orders.id", "op": "等于", "value": "1"},
                {"field": "bad", "op": "等于", "value": "2"},
            ],
            [
                {"left": "orders.person_id", "op": "等于", "right": "people.id"},
                {"left": "orders.id", "op": "等于", "right": "bad"},
            ],
            ["people.name", "bad"],
            fields,
        )
        self.assertEqual(state["conditions"], [{"field": "orders.id", "op": "等于", "value": "1"}])
        self.assertEqual(state["join_rules"], [{"left": "orders.person_id", "op": "等于", "right": "people.id"}])
        self.assertEqual(state["output_fields"], ["people.name"])

    def test_output_field_helpers_keep_order_and_ignore_invalid_indexes(self):
        output_fields = add_advanced_filter_output_fields(
            ["orders.id"],
            ["orders.id", "people.name", "people.age"],
            [1, 0, 99, -1],
        )
        self.assertEqual(output_fields, ["orders.id", "people.name"])

        output_fields = add_all_advanced_filter_output_fields(
            output_fields,
            ["people.age", "people.name", "orders.total"],
        )
        self.assertEqual(output_fields, ["orders.id", "people.name", "people.age", "orders.total"])

        output_fields = remove_advanced_filter_output_fields(output_fields, [1, 99, -1, 3])
        self.assertEqual(output_fields, ["orders.id", "people.age"])


if __name__ == "__main__":
    unittest.main()
