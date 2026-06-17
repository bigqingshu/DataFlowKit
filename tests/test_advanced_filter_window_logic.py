# -*- coding: utf-8 -*-
import sqlite3
import tempfile
import unittest
from pathlib import Path

from workflow.advanced_filter_window_logic import (
    build_advanced_filter_result_records,
    eval_advanced_filter_condition,
    eval_advanced_filter_conditions,
    eval_advanced_filter_join_rule,
    eval_advanced_filter_join_rules,
    load_advanced_filter_table_records,
    parse_advanced_filter_number,
    parse_positive_int_setting,
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


if __name__ == "__main__":
    unittest.main()
