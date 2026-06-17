# -*- coding: utf-8 -*-
import unittest

from core.data_utils import (
    make_unique_headers,
    make_unique_headers_for_append,
    normalize_rows,
    safe_cell,
)
from core.text_utils import make_sql_columns, quote_ident, sanitize_sql_name


class CoreUtilsTests(unittest.TestCase):
    def test_sanitize_sql_name_preserves_chinese_and_prefixes_digits(self):
        self.assertEqual(sanitize_sql_name("客户 名称", "默认"), "客户_名称")
        self.assertEqual(sanitize_sql_name("123字段", "默认"), "t_123字段")
        self.assertEqual(sanitize_sql_name("", "默认"), "默认")

    def test_make_sql_columns_deduplicates_sanitized_names(self):
        self.assertEqual(
            make_sql_columns(["字段", "字段", "字段 A", "字段-A", ""]),
            ["字段", "字段_2", "字段_A", "字段_A_2", "col_5"],
        )

    def test_quote_ident_escapes_double_quotes(self):
        self.assertEqual(quote_ident('a"b'), '"a""b"')

    def test_make_unique_headers_matches_table_manager_defaults(self):
        self.assertEqual(make_unique_headers(["", "字段", "字段", None]), ["列1", "字段", "字段_2", "列4"])

    def test_normalize_rows_and_safe_cell(self):
        rows = normalize_rows([[1], [2, 3, 4], [None, "x"]], 2)
        self.assertEqual(rows, [[1, ""], [2, 3], [None, "x"]])
        self.assertEqual(safe_cell(rows[0], 0), "1")
        self.assertEqual(safe_cell(rows[2], 0), "")
        self.assertEqual(safe_cell(rows[2], 5), "")

    def test_make_unique_headers_for_append_uses_suffix_from_two(self):
        self.assertEqual(
            make_unique_headers_for_append(["字段", "字段_2"], ["字段", "", "新增"]),
            ["字段_3", "字段_4", "新增"],
        )


if __name__ == "__main__":
    unittest.main()
