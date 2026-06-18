# -*- coding: utf-8 -*-
import unittest

from workflow.nodes import data_nodes
from workflow.nodes.data_common import (
    compare_values,
    ensure_column_count,
    ensure_field_exists,
    ensure_row_count,
    ensure_target_cell_limit,
    field_index,
    get_unique_header,
    parse_int,
    parse_row_number,
    parse_separator_text,
)


class DataCommonTests(unittest.TestCase):
    def test_common_helpers_keep_data_node_compat_exports(self):
        self.assertIs(data_nodes.field_index, field_index)
        self.assertIs(data_nodes.parse_separator_text, parse_separator_text)
        self.assertIs(data_nodes.compare_values, compare_values)

    def test_field_and_header_helpers(self):
        self.assertEqual(field_index(["A", "B"], "B"), 1)
        with self.assertRaisesRegex(ValueError, "字段不存在"):
            field_index(["A"], "B")
        self.assertEqual(get_unique_header("A", ["A", "A_2"]), "A_3")

    def test_row_and_column_expansion_helpers(self):
        headers, rows, index = ensure_field_exists(["A"], [["x"]], "B")
        self.assertEqual((headers, rows, index), (["A", "B"], [["x", ""]], 1))

        rows = ensure_row_count([["x"]], 2, 2)
        self.assertEqual(rows, [["x", ""], ["", ""]])

        headers, rows = ensure_column_count(["A"], [["x"]], 3, "列")
        self.assertEqual(headers, ["A", "列2", "列3"])
        self.assertEqual(rows, [["x", "", ""]])

        with self.assertRaisesRegex(ValueError, "超过安全上限"):
            ensure_target_cell_limit(2, 3, max_target_cells=5)

    def test_parse_and_compare_helpers(self):
        self.assertEqual(parse_int(" 12 ", "数量"), 12)
        with self.assertRaisesRegex(ValueError, "必须是整数"):
            parse_int("x", "数量")
        self.assertEqual(parse_row_number("1"), 1)
        with self.assertRaisesRegex(ValueError, "必须大于等于 1"):
            parse_row_number("0")
        self.assertEqual(parse_separator_text("{换行符}\\t"), "\n\t")
        self.assertTrue(compare_values("Alpha", "包含", "ph"))
        self.assertTrue(compare_values("10", "大于", "2"))


if __name__ == "__main__":
    unittest.main()
