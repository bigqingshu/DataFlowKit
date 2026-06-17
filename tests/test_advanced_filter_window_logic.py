# -*- coding: utf-8 -*-
import sqlite3
import tempfile
import unittest
from pathlib import Path

from workflow.advanced_filter_window_logic import (
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


if __name__ == "__main__":
    unittest.main()
