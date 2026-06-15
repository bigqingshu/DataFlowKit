# -*- coding: utf-8 -*-
import unittest
import threading
from datetime import datetime
from decimal import Decimal

from workflow.nodes.data_nodes import (
    apply_area_fill_node,
    apply_copy_column_node,
    apply_copy_row_node,
    apply_current_datetime_column_node,
    apply_delete_columns_node,
    apply_delete_rows_node,
    apply_dedupe_node,
    apply_extract_node,
    apply_filter_node,
    apply_format_datetime_node,
    apply_fill_value_node,
    apply_match_value_output_field_name_node,
    apply_merge_node,
    apply_move_columns_node,
    apply_new_columns_node,
    apply_numeric_column_node,
    apply_replace_node,
    apply_rename_columns_node,
    apply_row_data_mapping_node,
    apply_sequence_fill_node,
    build_filter_config_probe_result,
    build_filter_runtime_plan,
    build_plan_filter_right_index,
    choose_plan_filter_lookup_fields,
    collect_plan_filter_required_fields,
    extract_one_value,
    format_numeric_column_result,
    get_datetime_parse_warning,
    get_numeric_node_row_indexes,
    get_plan_filter_config_warnings,
    get_plan_filter_hash_join_rules,
    get_plan_filter_output_header_conflicts,
    get_plan_filter_output_headers,
    get_required_columns_for_plan_table,
    get_row_mapping_end_index,
    iter_plan_filter_join_candidates,
    make_current_table_records,
    match_value_output_column_match,
    normalize_plan_filter_config_field_references,
    record_passes_plan_conditions,
    record_passes_plan_join_rules,
    record_survives_available_plan_conditions,
    numeric_node_fallback_value,
    parse_format_datetime_value,
    parse_new_columns_specs,
    parse_numeric_value_for_column_op,
    render_current_datetime_template,
)


class WorkflowDataNodesTests(unittest.TestCase):
    def test_delete_columns_keeps_order_and_normalizes_short_rows(self):
        headers, rows, message = apply_delete_columns_node(
            ["A", "B", "C"],
            [["a1", "b1", "c1"], ["a2"]],
            {"fields": ["B"]},
        )

        self.assertEqual(headers, ["A", "C"])
        self.assertEqual(rows, [["a1", "c1"], ["a2", ""]])
        self.assertEqual(message, "删除 1 列")

    def test_delete_unknown_column_is_noop(self):
        headers, rows, message = apply_delete_columns_node(
            ["A", "B"],
            [["a", "b", "ignored"]],
            {"fields": ["X"]},
        )

        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["a", "b"]])
        self.assertEqual(message, "删除 0 列")

    def test_move_columns_appends_unspecified_columns(self):
        headers, rows, message = apply_move_columns_node(
            ["A", "B", "C"],
            [["a1", "b1", "c1"], ["a2", "b2"]],
            {"order": ["C", "A"]},
        )

        self.assertEqual(headers, ["C", "A", "B"])
        self.assertEqual(rows, [["c1", "a1", "b1"], ["", "a2", "b2"]])
        self.assertEqual(message, "已调整列顺序")

    def test_move_columns_ignores_unknown_order_fields(self):
        headers, rows, _message = apply_move_columns_node(
            ["A", "B"],
            [["a", "b"]],
            {"order": ["X", "B"]},
        )

        self.assertEqual(headers, ["B", "A"])
        self.assertEqual(rows, [["b", "a"]])

    def test_copy_column_creates_unique_field_and_applies_empty_default(self):
        headers, rows, message = apply_copy_column_node(
            ["A", "A_复制"],
            [[" x "], [""]],
            {
                "source_field": "A",
                "new_field": "A_复制",
                "trim_value": True,
                "empty_default": "空",
            },
        )

        self.assertEqual(headers, ["A", "A_复制", "A_复制_2"])
        self.assertEqual(rows, [[" x ", "", "x"], ["", "", "空"]])
        self.assertEqual(message, "复制列为新字段 A_复制_2")

    def test_copy_column_overwrites_existing_or_creates_target(self):
        headers, rows, message = apply_copy_column_node(
            ["A"],
            [["x"]],
            {
                "source_field": "A",
                "output_mode": "覆盖已有字段",
                "target_field": "B",
            },
        )

        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["x", "x"]])
        self.assertEqual(message, "复制列并覆盖字段 B")

    def test_copy_row_supports_insert_modes(self):
        headers, rows, message = apply_copy_row_node(
            ["A", "B"],
            [["a1", "b1"], ["a2", "b2"]],
            {"source_row": "1", "copy_count": "2", "insert_mode": "原行下方"},
        )

        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["a1", "b1"], ["a1", "b1"], ["a1", "b1"], ["a2", "b2"]])
        self.assertEqual(message, "复制第 1 行 2 次")

    def test_delete_rows_by_list_range_condition_and_empty_rows(self):
        headers, rows, message = apply_delete_rows_node(
            ["A", "B"],
            [["1", "x"], ["2", "y"], ["3", "z"]],
            {"delete_mode": "按行号列表", "row_spec": "1,3"},
        )
        self.assertEqual(rows, [["2", "y"]])
        self.assertEqual(message, "删除 2 行")

        _headers, rows, _message = apply_delete_rows_node(
            headers,
            [["1", "x"], ["2", "y"], ["3", "z"]],
            {"delete_mode": "按行号范围", "start_row": "2", "end_row": "3"},
        )
        self.assertEqual(rows, [["1", "x"]])

        _headers, rows, _message = apply_delete_rows_node(
            headers,
            [["abc", "x"], ["def", "y"]],
            {"delete_mode": "按条件删除", "condition_field": "A", "condition_op": "包含", "condition_value": "b"},
        )
        self.assertEqual(rows, [["def", "y"]])

        _headers, rows, _message = apply_delete_rows_node(
            headers,
            [[None, ""], ["x", ""], ["", ""]],
            {"delete_mode": "删除空行", "empty_mode": "整行为空"},
        )
        self.assertEqual(rows, [["x", ""]])

    def test_replace_node_manual_text_modes(self):
        headers, rows, message = apply_replace_node(
            ["Text"],
            [["abc abc"], ["ABC"]],
            {
                "target_field": "Text",
                "match_mode": "包含",
                "replace_mode": "局部替换匹配字符串",
                "match_value": "abc",
                "replace_value": "x",
                "replace_count": "1",
            },
        )

        self.assertEqual(headers, ["Text"])
        self.assertEqual(rows, [["x abc"], ["ABC"]])
        self.assertEqual(message, "修改 1 处")

        _headers, rows, message = apply_replace_node(
            ["Text"],
            [["ABC"], ["nope"]],
            {
                "target_field": "Text",
                "match_mode": "包含",
                "replace_mode": "整格替换为新值",
                "match_value": "abc",
                "replace_value": "matched",
                "case_sensitive": False,
            },
        )
        self.assertEqual(rows, [["matched"], ["nope"]])
        self.assertEqual(message, "修改 1 处")

    def test_replace_node_regex_and_invalid_regex_errors(self):
        headers, rows, message = apply_replace_node(
            ["Text"],
            [["A-001"], ["B-22"]],
            {
                "target_field": "Text",
                "match_mode": "正则匹配",
                "replace_mode": "局部替换匹配字符串",
                "match_value": r"\d+",
                "replace_value": "#",
            },
        )

        self.assertEqual(rows, [["A-#"], ["B-#"]])
        self.assertEqual(message, "修改 2 处")
        with self.assertRaisesRegex(ValueError, "批量替换正则错误"):
            apply_replace_node(
                ["Text"],
                [["abc"]],
                {
                    "target_field": "Text",
                    "match_mode": "正则匹配",
                    "match_value": "(",
                    "replace_value": "x",
                },
            )

    def test_replace_node_uses_column_values_by_current_and_pair_rows(self):
        headers, rows, message = apply_replace_node(
            ["Text", "Match", "Replace"],
            [["red apple", "red", "green"], ["blue berry", "berry", "bird"]],
            {
                "target_field": "Text",
                "match_value_source": "列字段",
                "match_value_field": "Match",
                "replace_value_source": "列字段",
                "replace_value_field": "Replace",
                "match_row_policy": "当前行",
                "replace_row_policy": "当前行",
                "match_mode": "包含",
            },
        )

        self.assertEqual(rows, [["green apple", "red", "green"], ["blue bird", "berry", "bird"]])
        self.assertEqual(message, "修改 2 处")

        _headers, rows, message = apply_replace_node(
            ["Text", "Match", "Replace"],
            [["foo red", "red", "R"], ["foo blue", "blue", "B"]],
            {
                "target_field": "Text",
                "match_value_source": "列字段",
                "match_value_field": "Match",
                "replace_value_source": "列字段",
                "replace_value_field": "Replace",
                "match_row_policy": "按匹配行号",
                "replace_row_policy": "按匹配行号",
                "match_mode": "包含",
            },
        )
        self.assertEqual(rows, [["foo R", "red", "R"], ["foo B", "blue", "B"]])
        self.assertEqual(message, "修改 2 处")

    def test_replace_node_reports_empty_and_invalid_source_rows(self):
        headers, rows, message = apply_replace_node(
            ["Text", "Match", "Replace"],
            [["abc", "", "x"], ["abc", "a", "y"]],
            {
                "target_field": "Text",
                "match_value_source": "列字段",
                "match_value_field": "Match",
                "replace_value_source": "列字段",
                "replace_value_field": "Replace",
                "match_mode": "包含",
                "match_row_policy": "按匹配行号",
                "replace_row_policy": "当前行",
            },
        )

        self.assertEqual(rows, [["xbc", "", "x"], ["ybc", "a", "y"]])
        self.assertEqual(message, "修改 2 处，跳过空匹配值 2 次")

        _headers, rows, message = apply_replace_node(
            ["Text", "Match", "Replace"],
            [["abc", "", "x"], ["abc", "a", "y"]],
            {
                "target_field": "Text",
                "match_value_source": "列字段",
                "match_value_field": "Match",
                "replace_value_source": "列字段",
                "replace_value_field": "Replace",
                "match_mode": "包含",
                "match_row_policy": "按匹配行号",
                "replace_row_policy": "固定行号",
                "replace_row_index": "99",
            },
        )

        self.assertEqual(rows, [["abc", "", "x"], ["abc", "a", "y"]])
        self.assertEqual(message, "修改 0 处，跳过无效取行 4 次")

    def test_replace_node_honors_cancel_callback(self):
        cancel_event = threading.Event()
        cancel_event.set()
        with self.assertRaisesRegex(RuntimeError, "用户取消"):
            apply_replace_node(
                ["Text"],
                [["abc"]],
                {
                    "target_field": "Text",
                    "match_mode": "包含",
                    "match_value": "a",
                    "replace_value": "x",
                },
                context={
                    "check_cancelled": lambda _index: (
                        (_ for _ in ()).throw(RuntimeError("用户取消")) if cancel_event.is_set() else None
                    )
                },
            )

    def test_merge_node_skips_empty_values_and_keeps_original_separator_gap(self):
        headers, rows, message = apply_merge_node(
            ["A", "B", "C"],
            [[" left ", "", "right"], ["", "mid", "end"]],
            {
                "fields": ["A", "B", "C"],
                "separators": ["-", "|"],
                "output_field": "Merged",
                "skip_empty": True,
                "trim_value": True,
            },
        )

        self.assertEqual(headers, ["A", "B", "C", "Merged"])
        self.assertEqual(rows, [[" left ", "", "right", "left-right"], ["", "mid", "end", "mid|end"]])
        self.assertEqual(message, "新增字段 Merged")

    def test_merge_node_can_keep_empty_values_and_use_placeholders(self):
        headers, rows, message = apply_merge_node(
            ["A", "B", "C"],
            [["a", "", "c"], ["", "", ""]],
            {
                "fields": ["A", "B", "C"],
                "separators": ["{空格}", "{制表符}"],
                "output_field": "A",
                "skip_empty": False,
                "trim_value": True,
                "empty_placeholder": "NA",
            },
        )

        self.assertEqual(headers, ["A", "B", "C", "A_2"])
        self.assertEqual(rows, [["a", "", "c", "a NA\tc"], ["", "", "", "NA NA\tNA"]])
        self.assertEqual(message, "新增字段 A_2")

    def test_merge_node_parses_escaped_separators_and_validates_fields(self):
        headers, rows, _message = apply_merge_node(
            ["A", "B"],
            [["a", "b"]],
            {
                "fields": ["A", "B"],
                "separators": ["\\n"],
                "output_field": "Merged",
            },
        )

        self.assertEqual(headers, ["A", "B", "Merged"])
        self.assertEqual(rows, [["a", "b", "a\nb"]])
        with self.assertRaisesRegex(ValueError, "合并字段不能为空"):
            apply_merge_node(["A"], [["a"]], {"fields": []})
        with self.assertRaisesRegex(ValueError, "字段不存在：Missing"):
            apply_merge_node(["A"], [["a"]], {"fields": ["Missing"]})

    def test_merge_node_honors_cancel_callback(self):
        cancel_event = threading.Event()
        cancel_event.set()
        with self.assertRaisesRegex(RuntimeError, "用户取消"):
            apply_merge_node(
                ["A", "B"],
                [["a", "b"]],
                {"fields": ["A", "B"]},
                context={
                    "check_cancelled": lambda _index: (
                        (_ for _ in ()).throw(RuntimeError("用户取消")) if cancel_event.is_set() else None
                    )
                },
            )

    def test_rename_columns_node_manual_mapping_warns_and_dedupes(self):
        headers, rows, message = apply_rename_columns_node(
            ["A", "B", "C"],
            [["a", "b", "c"]],
            {
                "mode": "手动映射改名",
                "mappings": [
                    {"old": "A", "new": " X "},
                    {"old": "B", "new": "X"},
                    {"old": "Missing", "new": "Y"},
                ],
                "trim_names": True,
                "duplicate_policy": "自动追加编号",
                "missing_policy": "跳过并记录警告",
            },
        )

        self.assertEqual(headers, ["X", "X_2", "C"])
        self.assertEqual(rows, [["a", "b", "c"]])
        self.assertEqual(message, "已更改 2 个字段名，警告 1 项")

    def test_rename_columns_node_missing_and_duplicate_errors(self):
        with self.assertRaisesRegex(ValueError, "字段不存在：Missing"):
            apply_rename_columns_node(
                ["A"],
                [["a"]],
                {
                    "mode": "手动映射改名",
                    "mappings": [{"old": "Missing", "new": "X"}],
                    "missing_policy": "报错并停止",
                },
            )

        with self.assertRaisesRegex(ValueError, "字段名重复：X"):
            apply_rename_columns_node(
                ["A", "B"],
                [["a", "b"]],
                {
                    "mode": "手动映射改名",
                    "mappings": [{"old": "A", "new": "X"}, {"old": "B", "new": "X"}],
                    "duplicate_policy": "报错并停止",
                },
            )

    def test_rename_columns_node_prefix_suffix_and_scope(self):
        headers, rows, message = apply_rename_columns_node(
            ["A", "B", "C"],
            [["a", "b", "c"]],
            {
                "mode": "批量添加前缀",
                "prefix": "src_",
                "scope": "选中字段",
                "scope_fields": ["A", "C"],
            },
        )

        self.assertEqual(headers, ["src_A", "B", "src_C"])
        self.assertEqual(rows, [["a", "b", "c"]])
        self.assertEqual(message, "已更改 2 个字段名")

        headers, rows, message = apply_rename_columns_node(
            ["A", "B"],
            [["a", "b"]],
            {"mode": "批量添加后缀", "suffix": "_out"},
        )
        self.assertEqual(headers, ["A_out", "B_out"])
        self.assertEqual(message, "已更改 2 个字段名")

    def test_rename_columns_node_replace_characters_and_empty_fallback(self):
        headers, rows, message = apply_rename_columns_node(
            ["old_A", "old_B", "C"],
            [["a", "b", "c"]],
            {
                "mode": "批量替换字段名字符",
                "replace_match": "old_",
                "replace_value": "",
            },
        )

        self.assertEqual(headers, ["A", "B", "C"])
        self.assertEqual(message, "已更改 2 个字段名")

        headers, rows, message = apply_rename_columns_node(
            ["A"],
            [["a"]],
            {
                "mode": "手动映射改名",
                "mappings": [{"old": "A", "new": "   "}],
                "trim_names": True,
            },
        )
        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["a"]])
        self.assertEqual(message, "已更改 0 个字段名")

        headers, rows, message = apply_rename_columns_node(
            ["A"],
            [["a"]],
            {
                "mode": "批量添加前缀",
                "prefix": "",
                "trim_names": True,
            },
        )
        self.assertEqual(headers, ["A"])
        self.assertEqual(message, "已更改 0 个字段名")

        headers, rows, message = apply_rename_columns_node(
            ["A"],
            [["a"]],
            {
                "mode": "手动映射改名",
                "mappings": [{"old": "A", "new": ""}],
            },
        )
        self.assertEqual(headers, ["A"])
        self.assertEqual(message, "已更改 0 个字段名")

    def test_rename_columns_node_empty_replace_match_is_noop(self):
        headers, rows, message = apply_rename_columns_node(
            ["A"],
            [["a"]],
            {
                "mode": "批量替换字段名字符",
                "replace_match": "",
                "replace_value": "X",
            },
        )

        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["a"]])
        self.assertEqual(message, "字段名替换匹配值为空，未修改")

    def test_numeric_helpers_parse_and_format_decimal_values(self):
        self.assertEqual(parse_numeric_value_for_column_op(" 123456789012345678 "), Decimal("123456789012345678"))
        self.assertEqual(parse_numeric_value_for_column_op("1.2300"), Decimal("1.2300"))

        with self.assertRaisesRegex(ValueError, "空值"):
            parse_numeric_value_for_column_op("")
        with self.assertRaisesRegex(ValueError, "不是有效数字：abc"):
            parse_numeric_value_for_column_op("abc")

        self.assertEqual(format_numeric_column_result(Decimal("10.0"), {"decimal_places": "自动"}), "10")
        self.assertEqual(format_numeric_column_result(Decimal("1.2300"), {"decimal_places": "自动"}), "1.23")
        self.assertEqual(format_numeric_column_result(Decimal("1.235"), {"decimal_places": "2"}), "1.24")
        self.assertEqual(format_numeric_column_result(Decimal("1.235"), {"decimal_places": "bad"}), "1")

    def test_numeric_helpers_resolve_row_ranges(self):
        headers = ["A", "Ref"]
        rows = [["1", "x"], ["2", ""], ["3", "y"], ["4", ""]]

        self.assertEqual(get_numeric_node_row_indexes(headers, rows, {"range_mode": "全部行"}), [0, 1, 2, 3])
        self.assertEqual(
            get_numeric_node_row_indexes(
                headers,
                rows,
                {"range_mode": "指定起止行", "start_row": "3", "end_row": "2"},
            ),
            [1, 2],
        )
        self.assertEqual(
            get_numeric_node_row_indexes(
                headers,
                rows,
                {
                    "range_mode": "填充到参考列数据边界",
                    "start_row": "2",
                    "reference_field": "Ref",
                },
            ),
            [1, 2],
        )
        self.assertEqual(get_numeric_node_row_indexes(headers, [], {"range_mode": "全部行"}), [])

    def test_numeric_fallback_value_policies(self):
        self.assertEqual(numeric_node_fallback_value("old", "保留原值", "fixed", "计算失败"), "old")
        self.assertEqual(numeric_node_fallback_value("old", "填写固定值", "fixed", "计算失败"), "fixed")
        self.assertEqual(numeric_node_fallback_value("old", "标记为计算失败", "fixed", "计算失败"), "计算失败")
        self.assertEqual(numeric_node_fallback_value("old", "标记为除零错误", "fixed", "除零错误"), "除零错误")
        self.assertEqual(numeric_node_fallback_value("old", "留空", "fixed", "计算失败"), "")

    def test_numeric_column_node_keeps_long_integer_precision(self):
        headers, rows, message = apply_numeric_column_node(
            ["N"],
            [["123456789012345678"]],
            {
                "target_field": "N",
                "output_field": "Out",
                "operation": "加",
                "operand_source": "固定值",
                "operand_value": "1",
                "decimal_places": "自动",
            },
        )

        self.assertEqual(headers, ["N", "Out"])
        self.assertEqual(rows, [["123456789012345678", "123456789012345679"]])
        self.assertEqual(message, "列数字运算完成：成功 1 行")

    def test_numeric_column_node_output_modes_and_operand_sources(self):
        headers, rows, message = apply_numeric_column_node(
            ["N", "Out"],
            [["2", ""], ["3", "old"]],
            {
                "target_field": "N",
                "output_mode": "写入已有字段",
                "output_field": "Out",
                "operation": "乘",
                "operand_source": "序号",
                "sequence_start": "10",
                "sequence_step": "5",
            },
        )

        self.assertEqual(headers, ["N", "Out"])
        self.assertEqual(rows, [["2", "20"], ["3", "45"]])
        self.assertEqual(message, "列数字运算完成：成功 2 行")

        headers, rows, message = apply_numeric_column_node(
            ["N"],
            [["5"], ["6"]],
            {
                "target_field": "N",
                "output_mode": "覆盖原字段",
                "operation": "减",
                "operand_source": "行号+N",
                "row_offset": "1",
            },
        )

        self.assertEqual(headers, ["N"])
        self.assertEqual(rows, [["3"], ["3"]])
        self.assertEqual(message, "列数字运算完成：成功 2 行")

    def test_numeric_column_node_range_other_field_failures_and_divide_zero(self):
        headers, rows, message = apply_numeric_column_node(
            ["N", "Operand", "Ref"],
            [["10", "2", "x"], ["bad", "3", "x"], ["30", "0", ""], ["40", "5", ""]],
            {
                "target_field": "N",
                "output_field": "Out",
                "operation": "除",
                "operand_source": "另一列同行数值",
                "operand_field": "Operand",
                "range_mode": "填充到参考列数据边界",
                "reference_field": "Ref",
                "non_number_policy": "标记为计算失败",
                "divide_zero_policy": "标记为除零错误",
                "decimal_places": "自动",
            },
        )

        self.assertEqual(headers, ["N", "Operand", "Ref", "Out"])
        self.assertEqual(rows, [["10", "2", "x", "5"], ["bad", "3", "x", "计算失败"], ["30", "0", "", ""], ["40", "5", "", ""]])
        self.assertEqual(message, "列数字运算完成：成功 1 行，非数字/运算失败 1 行")

        headers, rows, message = apply_numeric_column_node(
            ["N", "Operand"],
            [["10", "0"]],
            {
                "target_field": "N",
                "output_field": "Out",
                "operation": "除",
                "operand_source": "另一列同行数值",
                "operand_field": "Operand",
                "divide_zero_policy": "填写固定值",
                "divide_zero_fixed": "ZERO",
            },
        )

        self.assertEqual(rows, [["10", "0", "ZERO"]])
        self.assertEqual(message, "列数字运算完成：成功 0 行，除零 1 行")

    def test_numeric_column_node_empty_range_invalid_defaults_and_cancel_callback(self):
        headers, rows, message = apply_numeric_column_node(
            ["N"],
            [["2"]],
            {
                "target_field": "N",
                "output_field": "Out",
                "range_mode": "指定起止行",
                "start_row": "3",
                "end_row": "4",
                "operation": "加",
                "operand_source": "固定值",
                "operand_value": "bad",
            },
        )

        self.assertEqual(headers, ["N", "Out"])
        self.assertEqual(rows, [["2", ""]])
        self.assertEqual(message, "列数字运算完成：成功 0 行，处理范围为空")

        headers, rows, message = apply_numeric_column_node(
            ["N"],
            [["2"]],
            {
                "target_field": "N",
                "output_field": "Out",
                "operation": "加",
                "operand_source": "固定值",
                "operand_value": "bad",
            },
        )
        self.assertEqual(rows, [["2", "2"]])
        self.assertEqual(message, "列数字运算完成：成功 1 行")

        with self.assertRaisesRegex(RuntimeError, "用户取消"):
            apply_numeric_column_node(
                ["N"],
                [["2"]],
                {
                    "target_field": "N",
                    "output_field": "Out",
                },
                context={"check_cancelled": lambda _index: (_ for _ in ()).throw(RuntimeError("用户取消"))},
            )

    def test_dedupe_node_outputs_deduped_rows_by_key(self):
        headers, rows, message = apply_dedupe_node(
            ["ID", "Name"],
            [["A", "x"], [" A ", "y"], ["B", "z"], ["", "blank"]],
            {
                "key_fields": ["ID"],
                "trim": True,
                "output_mode": "输出去重后的数据",
                "add_marker_columns": False,
            },
        )

        self.assertEqual(headers, ["ID", "Name"])
        self.assertEqual(rows, [["A", "x"], ["B", "z"], ["", "blank"]])
        self.assertEqual(message, "去重完成：原 4 行，输出 3 行，重复组 1 个，重复行 2 行，模式：输出去重后的数据")

    def test_dedupe_node_keep_last_and_non_empty_count(self):
        headers, rows, message = apply_dedupe_node(
            ["ID", "A", "B"],
            [["K", "first", ""], ["K", "last", "x"], ["U", "", ""]],
            {
                "key_fields": ["ID"],
                "keep_policy": "保留最后一条",
                "output_mode": "输出去重后的数据",
                "add_marker_columns": False,
            },
        )

        self.assertEqual(rows, [["K", "last", "x"], ["U", "", ""]])
        self.assertEqual(message, "去重完成：原 3 行，输出 2 行，重复组 1 个，重复行 2 行，模式：输出去重后的数据")

        headers, rows, message = apply_dedupe_node(
            ["ID", "A", "B"],
            [["K", "first", ""], ["K", "", ""], ["K", "more", "x"]],
            {
                "key_fields": ["ID"],
                "keep_policy": "保留非空字段最多",
                "output_mode": "输出去重后的数据",
                "add_marker_columns": False,
            },
        )

        self.assertEqual(rows, [["K", "more", "x"]])
        self.assertEqual(message, "去重完成：原 3 行，输出 1 行，重复组 1 个，重复行 3 行，模式：输出去重后的数据")

    def test_dedupe_node_marker_columns_and_unique_names(self):
        headers, rows, message = apply_dedupe_node(
            ["ID", "重复组编号"],
            [["A", "old"], ["A", "old2"], ["B", "unique"]],
            {
                "key_fields": ["ID"],
                "output_mode": "原表增加重复标记列",
                "duplicate_group_field": "重复组编号",
            },
        )

        self.assertEqual(headers, ["ID", "重复组编号", "重复组编号_2", "重复状态", "组内序号", "重复次数", "是否保留"])
        self.assertEqual(rows[0], ["A", "old", "DUP_0001", "重复", "1", "2", "是"])
        self.assertEqual(rows[1], ["A", "old2", "DUP_0001", "重复", "2", "2", "否"])
        self.assertEqual(rows[2], ["B", "unique", "", "唯一", "1", "1", "是"])
        self.assertEqual(message, "去重完成：原 3 行，输出 3 行，重复组 1 个，重复行 2 行，模式：增加重复标记列")

    def test_dedupe_node_duplicate_unique_and_stat_outputs(self):
        headers, rows, message = apply_dedupe_node(
            ["ID", "Name"],
            [["A", "x"], ["A", "y"], ["B", "z"], ["C", "w"]],
            {"key_fields": ["ID"], "output_mode": "输出重复项数据", "add_marker_columns": False},
        )

        self.assertEqual(headers, ["ID", "Name"])
        self.assertEqual(rows, [["A", "x"], ["A", "y"]])
        self.assertEqual(message, "去重完成：原 4 行，输出 2 行，重复组 1 个，重复行 2 行，模式：输出重复项数据")

        headers, rows, message = apply_dedupe_node(
            ["ID", "Name"],
            [["A", "x"], ["A", "y"], ["B", "z"], ["C", "w"]],
            {"key_fields": ["ID"], "output_mode": "输出唯一项数据", "add_marker_columns": False},
        )

        self.assertEqual(rows, [["B", "z"], ["C", "w"]])
        self.assertEqual(message, "去重完成：原 4 行，输出 2 行，重复组 1 个，重复行 2 行，模式：输出唯一项数据")

        headers, rows, message = apply_dedupe_node(
            ["ID", "Name"],
            [["A", "x"], ["A", "y"], ["B", "z"], ["", "blank"]],
            {
                "key_fields": ["ID"],
                "empty_key_policy": "空键跳过去重",
                "output_mode": "输出重复统计表",
            },
        )

        self.assertEqual(headers, ["ID", "重复次数", "重复组编号", "是否重复"])
        self.assertEqual(rows, [["A", "2", "DUP_0001", "是"], ["B", "1", "", "否"], ["", "1", "", "空键跳过"]])
        self.assertEqual(message, "去重统计：共 3 个统计项，重复组 1 个")

    def test_dedupe_node_errors_empty_table_and_cancel_callback(self):
        headers, rows, message = apply_dedupe_node([], [["extra"]], {})

        self.assertEqual(headers, [])
        self.assertEqual(rows, [[]])
        self.assertEqual(message, "去重：无字段，未处理")

        with self.assertRaisesRegex(ValueError, "去重节点需要至少选择一个去重字段"):
            apply_dedupe_node(["A"], [["x"]], {"key_fields": []})
        with self.assertRaisesRegex(ValueError, "去重字段不存在：Missing"):
            apply_dedupe_node(["A"], [["x"]], {"key_fields": ["Missing"]})
        with self.assertRaisesRegex(RuntimeError, "用户取消"):
            apply_dedupe_node(
                ["A"],
                [["x"]],
                {"key_fields": ["A"]},
                context={"check_cancelled": lambda _index: (_ for _ in ()).throw(RuntimeError("用户取消"))},
            )

    def test_match_value_output_match_modes(self):
        self.assertTrue(match_value_output_column_match("ABC", "ABC", "完全相等"))
        self.assertTrue(match_value_output_column_match("ABC", "bc", "忽略大小写当前值包含匹配值"))
        self.assertTrue(match_value_output_column_match("abc123", r"\d+", "正则匹配"))
        self.assertFalse(match_value_output_column_match("abc", "(", "正则匹配"))
        self.assertFalse(match_value_output_column_match("abc", "x", "完全相等"))

    def test_match_value_output_node_writes_single_multi_and_no_match(self):
        lookup_context = {
            "lookup_columns": ["ColA", "ColB"],
            "lookup_records": [
                {"__row_index__": 1, "ColA": "alpha", "ColB": "beta"},
                {"__row_index__": 2, "ColA": "gamma", "ColB": "alpha"},
            ],
        }

        headers, rows, message = apply_match_value_output_field_name_node(
            ["Source"],
            [["beta"], ["alpha"], ["none"]],
            {
                "source_field": "Source",
                "lookup_table": "lookup",
                "lookup_fields": ["ColA", "ColB"],
                "match_mode": "完全相等",
                "multi_match_policy": "合并所有字段名",
                "multi_match_separator": "|",
            },
            context=lookup_context,
        )

        self.assertEqual(headers, ["Source", "匹配字段名", "匹配值", "匹配行号", "匹配状态"])
        self.assertEqual(rows[0], ["beta", "ColB", "beta", "1", "成功"])
        self.assertEqual(rows[1], ["alpha", "ColA|ColB", "alpha", "1|2", "多匹配，共2项"])
        self.assertEqual(rows[2], ["none", "未匹配", "", "", "未匹配"])
        self.assertEqual(message, "匹配值输出列名完成：成功 1 行，多匹配 1 行，未匹配 1 行")

    def test_match_value_output_node_multi_policies_and_existing_fields(self):
        lookup_context = {
            "lookup_columns": ["A", "B"],
            "lookup_records": [
                {"__row_index__": 1, "A": "x", "B": "x"},
            ],
        }

        headers, rows, message = apply_match_value_output_field_name_node(
            ["Source", "Out", "Status"],
            [["x", "old", "old-status"]],
            {
                "source_field": "Source",
                "lookup_table": "lookup",
                "lookup_fields": ["A", "B"],
                "output_field": "Out",
                "output_match_value": False,
                "output_match_row": False,
                "output_status": True,
                "status_field": "Status",
                "multi_match_policy": "取第一个匹配字段名",
            },
            context=lookup_context,
        )

        self.assertEqual(headers, ["Source", "Out", "Status"])
        self.assertEqual(rows, [["x", "A", "多匹配取第一，共2项"]])
        self.assertEqual(message, "匹配值输出列名完成：成功 0 行，多匹配 1 行，未匹配 0 行")

        headers, rows, message = apply_match_value_output_field_name_node(
            ["Source"],
            [["x"]],
            {
                "source_field": "Source",
                "lookup_table": "lookup",
                "lookup_fields": ["A", "B"],
                "multi_match_policy": "标记为多匹配",
            },
            context=lookup_context,
        )

        self.assertEqual(rows, [["x", "多匹配", "x", "1", "多匹配，共2项"]])
        self.assertEqual(message, "匹配值输出列名完成：成功 0 行，多匹配 1 行，未匹配 0 行")

    def test_match_value_output_node_skip_empty_lookup_and_contains_modes(self):
        lookup_context = {
            "lookup_columns": ["Needle", "Text"],
            "lookup_records": [
                {"__row_index__": 1, "Needle": "", "Text": "hello world"},
                {"__row_index__": 2, "Needle": "world", "Text": "other"},
            ],
        }

        headers, rows, message = apply_match_value_output_field_name_node(
            ["Source"],
            [["hello world"]],
            {
                "source_field": "Source",
                "lookup_table": "lookup",
                "lookup_fields": ["Needle"],
                "match_mode": "当前值包含匹配值",
                "skip_empty_lookup_value": True,
            },
            context=lookup_context,
        )

        self.assertEqual(rows, [["hello world", "Needle", "world", "2", "成功"]])
        self.assertEqual(message, "匹配值输出列名完成：成功 1 行，多匹配 0 行，未匹配 0 行")

        headers, rows, message = apply_match_value_output_field_name_node(
            ["Source"],
            [["hello"]],
            {
                "source_field": "Source",
                "lookup_table": "lookup",
                "lookup_fields": ["Text"],
                "match_mode": "匹配值包含当前值",
                "no_match_value": "MISS",
            },
            context=lookup_context,
        )

        self.assertEqual(rows, [["hello", "Text", "hello world", "1", "成功"]])
        self.assertEqual(message, "匹配值输出列名完成：成功 1 行，多匹配 0 行，未匹配 0 行")

    def test_match_value_output_node_errors_and_cancel_callback(self):
        lookup_context = {"lookup_columns": ["A"], "lookup_records": [{"__row_index__": 1, "A": "x"}]}

        with self.assertRaisesRegex(ValueError, "请选择当前表匹配字段"):
            apply_match_value_output_field_name_node(["Source"], [["x"]], {"lookup_table": "lookup", "lookup_fields": ["A"]}, context=lookup_context)
        with self.assertRaisesRegex(ValueError, "当前表字段不存在：Missing"):
            apply_match_value_output_field_name_node(["Source"], [["x"]], {"source_field": "Missing", "lookup_table": "lookup", "lookup_fields": ["A"]}, context=lookup_context)
        with self.assertRaisesRegex(ValueError, "请选择匹配表或中转副表"):
            apply_match_value_output_field_name_node(["Source"], [["x"]], {"source_field": "Source", "lookup_fields": ["A"]}, context=lookup_context)
        with self.assertRaisesRegex(ValueError, "请选择至少一个参与匹配的目标表字段"):
            apply_match_value_output_field_name_node(["Source"], [["x"]], {"source_field": "Source", "lookup_table": "lookup"}, context=lookup_context)
        with self.assertRaisesRegex(ValueError, "匹配表字段不存在：Missing"):
            apply_match_value_output_field_name_node(["Source"], [["x"]], {"source_field": "Source", "lookup_table": "lookup", "lookup_fields": ["Missing"]}, context=lookup_context)
        with self.assertRaisesRegex(RuntimeError, "用户取消"):
            apply_match_value_output_field_name_node(
                ["Source"],
                [["x"]],
                {"source_field": "Source", "lookup_table": "lookup", "lookup_fields": ["A"]},
                context={
                    "lookup_columns": ["A"],
                    "lookup_records": [{"__row_index__": 1, "A": "x"}],
                    "check_cancelled": lambda _index: (_ for _ in ()).throw(RuntimeError("用户取消")),
                },
            )

    def test_row_mapping_end_index_modes(self):
        rows = [["a"], ["b"], ["c"]]

        self.assertEqual(get_row_mapping_end_index(rows, 1, {"end_mode": "固定行数", "count": "5"}), 2)
        self.assertEqual(get_row_mapping_end_index(rows, 0, {"end_mode": "填充到指定行", "end_row": "2"}), 1)
        self.assertEqual(get_row_mapping_end_index(rows, 1, {"end_mode": "填充到指定行", "end_row": "1"}), 1)
        self.assertEqual(get_row_mapping_end_index([], 0, {}), -1)

    def test_row_data_mapping_expands_values_with_keep_fields(self):
        headers, rows, message = apply_row_data_mapping_node(
            ["ID", "A", "B"],
            [["R1", " x ", ""], ["R2", "y", "z"]],
            {
                "keep_fields": ["ID"],
                "value_fields": ["A", "B"],
                "start_row": "1",
                "end_mode": "填充到数据边界",
                "empty_mode": "跳过空值",
                "trim_value": True,
            },
        )

        self.assertEqual(headers, ["ID", "原始行号", "来源字段", "输出内容", "状态"])
        self.assertEqual(rows, [["R1", "1", "A", "x", "成功"], ["R2", "2", "A", "y", "成功"], ["R2", "2", "B", "z", "成功"]])
        self.assertEqual(message, "按行取值展开 3 行，跳过空值 1 个")

    def test_row_data_mapping_empty_fixed_and_column_toggles(self):
        headers, rows, message = apply_row_data_mapping_node(
            ["ID", "A", "B"],
            [["R1", "", " b "]],
            {
                "keep_fields": ["ID"],
                "value_fields": ["A", "B"],
                "start_row": "1",
                "empty_mode": "填写固定值",
                "empty_fixed": "NA",
                "trim_value": False,
                "output_original_row": False,
                "output_source_field": False,
                "output_status": False,
                "output_value_field": "ID",
            },
        )

        self.assertEqual(headers, ["ID", "ID_2"])
        self.assertEqual(rows, [["R1", "NA"], ["R1", " b "]])
        self.assertEqual(message, "按行取值展开 2 行")

    def test_row_data_mapping_end_modes_and_empty_row_stop(self):
        headers, rows, message = apply_row_data_mapping_node(
            ["ID", "A"],
            [["R1", "a"], ["", ""], ["R3", "c"]],
            {
                "keep_fields": ["ID"],
                "value_fields": ["A"],
                "start_row": "1",
                "end_mode": "遇到空行停止",
                "empty_mode": "保留空值",
            },
        )

        self.assertEqual(rows, [["R1", "1", "A", "a", "成功"]])
        self.assertEqual(message, "按行取值展开 1 行，遇到空行停止")

        headers, rows, message = apply_row_data_mapping_node(
            ["ID", "A"],
            [["R1", "a"], ["R2", "b"], ["R3", "c"]],
            {
                "keep_fields": ["ID"],
                "value_fields": ["A"],
                "start_row": "2",
                "end_mode": "固定行数",
                "count": "1",
            },
        )

        self.assertEqual(rows, [["R2", "2", "A", "b", "成功"]])
        self.assertEqual(message, "按行取值展开 1 行")

    def test_row_data_mapping_empty_data_and_errors(self):
        headers, rows, message = apply_row_data_mapping_node(["A"], [], {"value_fields": ["A"]})

        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [])
        self.assertEqual(message, "当前无数据，未展开")

        with self.assertRaisesRegex(ValueError, "请至少选择一个取值字段"):
            apply_row_data_mapping_node(["A"], [["x"]], {"value_fields": ["Missing"]})
        with self.assertRaisesRegex(ValueError, "起始行号超出当前数据范围"):
            apply_row_data_mapping_node(["A"], [["x"]], {"value_fields": ["A"], "start_row": "2"})

    def test_plan_filter_helpers_normalize_refs_and_output_headers(self):
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

    def test_plan_filter_helpers_conditions_and_join_rules(self):
        record = {"当前表.A": "x", "当前表.B": "x", "t.C": "xyz"}

        self.assertTrue(record_passes_plan_conditions(
            record,
            [{"field": "当前表.A", "op": "等于", "value_source": "字段值", "value": "当前表.B"}],
            "AND",
        ))
        self.assertFalse(record_passes_plan_conditions(
            record,
            [{"field": "当前表.A", "op": "等于", "value_source": "字段值", "value": "当前表.Missing"}],
            "AND",
        ))
        self.assertTrue(record_survives_available_plan_conditions(
            {"当前表.A": "x"},
            [
                {"field": "当前表.A", "op": "等于", "value": "x"},
                {"field": "t.C", "op": "等于", "value": "z"},
            ],
            "OR",
        ))
        self.assertTrue(record_passes_plan_join_rules(
            record,
            [{"left": "当前表.A", "op": "等于", "right": "当前表.B"}],
        ))
        self.assertTrue(record_passes_plan_join_rules(
            {"当前表.A": "x"},
            [{"left": "当前表.A", "op": "等于", "right": "t.C"}],
        ))
        self.assertFalse(record_passes_plan_join_rules(
            {"当前表.A": "x", "t.C": "y"},
            [{"left": "当前表.A", "op": "等于", "right": "t.C"}],
        ))

    def test_plan_filter_helpers_hash_join_and_required_fields(self):
        right_records = [{"t.C": "x", "t.Name": "n1"}, {"t.C": "y", "t.Name": "n2"}]
        join_rules = [{"left": "当前表.A", "op": "等于", "right": "t.C"}]
        hash_rules = get_plan_filter_hash_join_rules("t", join_rules, "AND", right_records)
        right_index, missing = build_plan_filter_right_index(right_records, hash_rules)

        self.assertEqual(hash_rules, [("当前表.A", "t.C")])
        self.assertEqual(missing, [])
        self.assertEqual(
            iter_plan_filter_join_candidates({"当前表.A": "x"}, right_records, hash_rules, right_index, missing),
            [right_records[0]],
        )
        self.assertEqual(get_required_columns_for_plan_table("t", ["C", "Name", "Other"], {"t.C", "t.Name"}), ["C", "Name"])

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

    def test_filter_runtime_plan_selects_fields_and_probe_result(self):
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

    def test_filter_node_filters_current_table_and_dedupes(self):
        headers, rows, message = apply_filter_node(
            ["A", "B"],
            [["x", "1"], ["x", "1"], ["y", "2"]],
            {
                "conditions": [{"field": "当前表.A", "op": "等于", "value": "x"}],
                "output_fields": ["当前表.A", "当前表.B"],
                "remove_duplicates": True,
            },
            context={
                "lookup_fields": ["当前表.A", "当前表.B"],
                "output_headers": ["A", "B"],
                "current_required": {"A", "B"},
                "table_required": {},
                "table_records": {},
            },
        )

        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["x", "1"]])
        self.assertEqual(message, "筛选/匹配后 1 行，已去除重复内容 1 行；优化：提前过滤 1 行")

    def test_filter_node_joins_loaded_table_records_with_hash_index(self):
        headers, rows, message = apply_filter_node(
            ["Code"],
            [["A"], ["B"]],
            {
                "conditions": [],
                "join_rules": [{"left": "当前表.Code", "op": "等于", "right": "t.Code"}],
                "extra_tables": ["t"],
                "output_fields": ["当前表.Code", "t.Name"],
            },
            context={
                "lookup_fields": ["当前表.Code", "t.Name"],
                "output_headers": ["Code", "t.Name"],
                "current_required": {"Code"},
                "table_required": {"t": {"t.Code", "t.Name"}},
                "table_records": {
                    "t": [
                        {"t.Code": "A", "t.Name": "Alpha"},
                        {"t.Code": "C", "t.Name": "Gamma"},
                    ]
                },
            },
        )

        self.assertEqual(headers, ["Code", "t.Name"])
        self.assertEqual(rows, [["A", "Alpha"]])
        self.assertEqual(message, "筛选/匹配后 1 行；优化：字段裁剪 1 表，等值索引匹配 1 表")

    def test_filter_node_rejects_large_cross_join_without_rules(self):
        with self.assertRaisesRegex(RuntimeError, "可能形成全组合"):
            apply_filter_node(
                ["A"],
                [["1"], ["2"]],
                {
                    "conditions": [],
                    "join_rules": [],
                    "extra_tables": ["t"],
                    "output_fields": ["当前表.A", "t.B"],
                    "max_intermediate": "3",
                },
                context={
                    "lookup_fields": ["当前表.A", "t.B"],
                    "output_headers": ["A", "t.B"],
                    "current_required": {"A"},
                    "table_required": {"t": {"t.B"}},
                    "table_records": {"t": [{"t.B": "x"}, {"t.B": "y"}]},
                },
            )

    def test_fill_value_manual_expands_rows_and_skips_existing_cells(self):
        headers, rows, message = apply_fill_value_node(
            ["A"],
            [["old"], [""]],
            {
                "target_field": "A",
                "value_source": "手动输入值",
                "manual_value": "new",
                "direction": "向下",
                "end_mode": "固定数量",
                "count": "3",
                "overwrite_rule": "只填充空单元格",
            },
        )

        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["old"], ["new"], ["new"]])
        self.assertEqual(message, "填充 2 个单元格，跳过 1 个")

    def test_fill_value_from_same_row_source_field(self):
        headers, rows, message = apply_fill_value_node(
            ["Source", "Target"],
            [["s1", ""], ["s2", "occupied"]],
            {
                "target_field": "Target",
                "value_source": "同行来源字段",
                "source_field": "Source",
                "direction": "向下",
                "end_mode": "固定数量",
                "count": "2",
                "overwrite_rule": "覆盖所有目标单元格",
            },
        )

        self.assertEqual(headers, ["Source", "Target"])
        self.assertEqual(rows, [["s1", "s1"], ["s2", "s2"]])
        self.assertEqual(message, "填充 2 个单元格，跳过 0 个")

    def test_fill_value_with_cycle_source_column_skips_empty_values(self):
        headers, rows, message = apply_fill_value_node(
            ["Source", "Target"],
            [["a", ""], ["", ""], ["b", ""], ["", ""]],
            {
                "target_field": "Target",
                "value_source": "循环源列填充",
                "source_field": "Source",
                "source_range_mode": "整体表格数据边界",
                "source_empty_mode": "跳过空值",
                "direction": "向下",
                "end_mode": "固定数量",
                "count": "4",
                "overwrite_rule": "覆盖所有目标单元格",
            },
        )

        self.assertEqual(rows, [["a", "a"], ["", "b"], ["b", "a"], ["", "b"]])
        self.assertEqual(message, "循环源列填充 4 个单元格，跳过 0 个，循环周期 2")

    def test_fill_value_copies_source_column_structure_to_new_field(self):
        headers, rows, message = apply_fill_value_node(
            ["Source"],
            [["x"], [""], ["z"]],
            {
                "target_field": "Copied",
                "value_source": "来源列完整结构",
                "source_field": "Source",
                "source_range_mode": "整体表格数据边界",
                "overwrite_rule": "覆盖所有目标单元格",
            },
        )

        self.assertEqual(headers, ["Source", "Copied"])
        self.assertEqual(rows, [["x", "x"], ["", ""], ["z", "z"]])
        self.assertEqual(message, "来源列完整结构填充 3 个单元格，跳过 0 个")

    def test_sequence_fill_supports_padding_prefix_suffix_and_skip_rule(self):
        headers, rows, message = apply_sequence_fill_node(
            ["Seq"],
            [[""], ["keep"], [""]],
            {
                "target_field": "Seq",
                "start_value": "7",
                "step": "2",
                "zero_pad": "3",
                "prefix": "NO-",
                "suffix": "-X",
                "direction": "向下",
                "end_mode": "固定数量",
                "count": "3",
                "overwrite_rule": "不覆盖已有数据，只跳过",
            },
        )

        self.assertEqual(headers, ["Seq"])
        self.assertEqual(rows, [["NO-007-X"], ["keep"], ["NO-009-X"]])
        self.assertEqual(message, "序列填充 2 个单元格，跳过 1 个")

    def test_sequence_fill_count_can_follow_source_column_data_count(self):
        headers, rows, message = apply_sequence_fill_node(
            ["Source", "Seq"],
            [["x", ""], ["", ""], ["y", ""], ["", ""]],
            {
                "target_field": "Seq",
                "start_value": "1",
                "step": "1",
                "count_source_mode": "来源列数据数量",
                "source_field": "Source",
                "source_range_mode": "来源列数据边界",
                "direction": "向下",
                "overwrite_rule": "覆盖所有目标单元格",
            },
        )

        self.assertEqual(rows, [["x", "1"], ["", "2"], ["y", "3"], ["", ""]])
        self.assertEqual(message, "序列填充 3 个单元格，跳过 0 个")

    def test_area_fill_manual_value_fills_rectangular_target(self):
        headers, rows, message = apply_area_fill_node(
            ["A", "B"],
            [["", ""], ["", "occupied"]],
            {
                "start_field": "A",
                "end_field": "B",
                "start_row": "1",
                "end_row": "2",
                "value_source": "手动输入值",
                "manual_value": "x",
                "overwrite_rule": "只填充空单元格",
            },
        )

        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["x", "x"], ["x", "occupied"]])
        self.assertEqual(message, "区域填充 3 个单元格，跳过 1 个")

    def test_area_fill_copies_source_area_and_expands_columns(self):
        headers, rows, message = apply_area_fill_node(
            ["S1", "S2", "T"],
            [["a1", "b1", ""], ["a2", "b2", ""]],
            {
                "start_field": "T",
                "end_field": "T",
                "start_row": "1",
                "value_source": "来源区域完整复制",
                "source_field": "S1",
                "source_end_field": "S2",
                "source_range_mode": "整体表格数据边界",
                "overwrite_rule": "覆盖所有目标单元格",
            },
        )

        self.assertEqual(headers, ["S1", "S2", "T", "区域复制列4"])
        self.assertEqual(rows, [["a1", "b1", "a1", "b1"], ["a2", "b2", "a2", "b2"]])
        self.assertEqual(message, "来源区域完整复制 4 个单元格，跳过 0 个")

    def test_area_fill_source_column_structure_spreads_to_target_columns(self):
        headers, rows, message = apply_area_fill_node(
            ["Source", "T1", "T2"],
            [["a", "", ""], ["b", "", ""], ["", "", ""]],
            {
                "start_field": "T1",
                "end_field": "T2",
                "start_row": "1",
                "value_source": "来源列完整结构",
                "source_field": "Source",
                "source_range_mode": "来源列数据边界",
                "overwrite_rule": "覆盖所有目标单元格",
            },
        )

        self.assertEqual(rows, [["a", "a", "a"], ["b", "b", "b"], ["", "", ""]])
        self.assertEqual(message, "来源列完整结构区域填充 4 个单元格，跳过 0 个")

    def test_area_fill_multi_field_row_horizontal_and_vertical(self):
        headers, rows, message = apply_area_fill_node(
            ["S1", "S2", "T1", "T2"],
            [["v1", "v2", "", ""], ["", "", "", ""]],
            {
                "start_field": "T1",
                "end_field": "T2",
                "start_row": "1",
                "end_row": "2",
                "value_source": "指定行多字段取值",
                "source_field": "S1",
                "source_end_field": "S2",
                "source_row": "1",
                "multi_field_fill_direction": "横向填充",
                "overwrite_rule": "覆盖所有目标单元格",
            },
        )
        self.assertEqual(rows, [["v1", "v2", "v1", "v2"], ["", "", "v1", "v2"]])
        self.assertEqual(message, "指定行多字段取值区域填充 4 个单元格，跳过 0 个")

        _headers, rows, message = apply_area_fill_node(
            headers,
            [["v1", "v2", "", ""], ["", "", "", ""]],
            {
                "start_field": "T1",
                "end_field": "T2",
                "start_row": "1",
                "value_source": "指定行多字段取值",
                "source_field": "S1",
                "source_end_field": "S2",
                "source_row": "1",
                "multi_field_fill_direction": "纵向填充",
                "overwrite_rule": "覆盖所有目标单元格",
            },
        )
        self.assertEqual(rows, [["v1", "v2", "v1", "v1"], ["", "", "v2", "v2"]])
        self.assertEqual(message, "指定行多字段取值区域填充 4 个单元格，跳过 0 个")

    def test_area_fill_cycles_multi_field_source_values(self):
        headers, rows, message = apply_area_fill_node(
            ["S1", "S2", "T1", "T2"],
            [["a", "b", "", ""], ["", "c", "", ""]],
            {
                "start_field": "T1",
                "end_field": "T2",
                "start_row": "1",
                "end_row": "2",
                "value_source": "循环源列填充",
                "source_field": "S1",
                "source_end_field": "S2",
                "source_range_mode": "整体表格数据边界",
                "source_empty_mode": "跳过空值",
                "overwrite_rule": "覆盖所有目标单元格",
            },
        )

        self.assertEqual(rows, [["a", "b", "a", "b"], ["", "c", "c", "a"]])
        self.assertEqual(message, "循环源列区域填充 4 个单元格，跳过 0 个，循环周期 3（多源字段）")

    def test_parse_new_columns_specs_supports_per_column_values(self):
        specs = parse_new_columns_specs(
            {
                "columns_text": " A = one \nB=two\nC",
                "value_mode": "按列配置值",
                "default_value": "default",
                "strip_column_name": True,
            }
        )

        self.assertEqual(specs, [("A", " one"), ("B", "two"), ("C", "default")])

    def test_new_columns_node_handles_conflicts(self):
        headers, rows, message = apply_new_columns_node(
            ["A"],
            [["old"], ["keep", "ignored"]],
            {
                "columns_text": "A=overwrite\nB=new",
                "value_mode": "按列配置值",
                "conflict_mode": "覆盖已有字段",
            },
        )

        self.assertEqual(headers, ["A", "B"])
        self.assertEqual(rows, [["overwrite", "new"], ["overwrite", "new"]])
        self.assertEqual(message, "新建列完成：新增 1 列，覆盖 1 列，跳过 0 列；字段：A, B")

        headers, rows, message = apply_new_columns_node(
            ["A"],
            [["old"]],
            {
                "columns_text": "A\nB",
                "default_value": "x",
                "conflict_mode": "自动改名",
            },
        )

        self.assertEqual(headers, ["A", "A_2", "B"])
        self.assertEqual(rows, [["old", "x", "x"]])
        self.assertEqual(message, "新建列完成：新增 2 列，覆盖 0 列，跳过 0 列；字段：A_2, B")

    def test_render_current_datetime_template_supports_tokens_and_strftime(self):
        dt = datetime(2026, 6, 15, 9, 8, 7, 123456)

        self.assertEqual(
            render_current_datetime_template(dt, {"template": "{YYYY}/{M}/{D} {HH}:{mm}:{ss}.{fff}"}),
            "2026/6/15 09:08:07.123",
        )
        self.assertEqual(
            render_current_datetime_template(
                dt,
                {"format_mode": "Python strftime", "strftime_template": "%Y%m%d-%H%M%S"},
            ),
            "20260615-090807",
        )

    def test_current_datetime_column_can_generate_or_overwrite(self):
        dt = datetime(2026, 6, 15, 9, 8, 7)
        headers, rows, message = apply_current_datetime_column_node(
            ["A"],
            [["x"], ["y"]],
            {
                "new_field": "Now",
                "template": "{YYYY}-{MM}-{DD} {HH}:{mm}:{ss}",
                "time_mode": "整次运行固定同一时间",
            },
            now_func=lambda: dt,
        )

        self.assertEqual(headers, ["A", "Now"])
        self.assertEqual(rows, [["x", "2026-06-15 09:08:07"], ["y", "2026-06-15 09:08:07"]])
        self.assertEqual(message, "新建日期时间列完成：字段【Now】，写入 2 行，示例：2026-06-15 09:08:07")

        headers, rows, message = apply_current_datetime_column_node(
            ["A"],
            [["old"]],
            {
                "output_mode": "覆盖已有字段",
                "target_field": "A",
                "format_mode": "Python strftime",
                "strftime_template": "%Y%m%d",
            },
            now_func=lambda: dt,
        )

        self.assertEqual(headers, ["A"])
        self.assertEqual(rows, [["20260615"]])
        self.assertEqual(message, "新建日期时间列完成：字段【A】，写入 1 行，示例：20260615")

    def test_format_datetime_node_fixed_date_generates_status_field(self):
        headers, rows, message = apply_format_datetime_node(
            ["Raw"],
            [["260615"], ["260631"]],
            {
                "source_field": "Raw",
                "parse_type": "日期",
                "input_structure": "固定位置",
                "year_start": "1",
                "year_len": "2",
                "month_start": "3",
                "month_len": "2",
                "day_start": "5",
                "day_len": "2",
                "year_rule": "20xx",
                "new_field": "Date",
                "output_template": "{YYYY}/{MM}/{DD}",
                "output_status": True,
                "status_field": "Status",
                "unmatched_mode": "填写固定值",
                "unmatched_fixed": "BAD",
            },
        )

        self.assertEqual(headers, ["Raw", "Date", "Status"])
        self.assertEqual(rows, [["260615", "2026/06/15", "成功"], ["260631", "BAD", "日期无效：2026-06-31"]])
        self.assertEqual(message, "格式规范化完成：写入 2 行，失败 1 行，跳过 0 行")

    def test_format_datetime_node_delimited_date_warns_about_ambiguous_order(self):
        headers, rows, message = apply_format_datetime_node(
            ["Raw"],
            [["03/06/26"]],
            {
                "source_field": "Raw",
                "parse_type": "日期",
                "input_structure": "分隔符",
                "date_delimiter": "自动识别",
                "date_order": "月-日-年",
                "year_rule": "20xx",
                "output_mode": "覆盖源字段",
                "output_template": "{YYYY}-{MM}-{DD}",
                "output_status": True,
            },
        )

        self.assertEqual(headers, ["Raw", "格式解析状态"])
        self.assertEqual(rows, [["2026-03-06", "成功但存在歧义：月和日均不超过12，请确认月日顺序"]])
        self.assertEqual(message, "格式规范化完成：写入 1 行，失败 0 行，跳过 0 行")

    def test_format_datetime_node_outputs_component_columns_for_separate_time_field(self):
        headers, rows, message = apply_format_datetime_node(
            ["Date", "Time"],
            [["2026-06-15", "09:08:07"]],
            {
                "source_field": "Date",
                "time_source_field": "Time",
                "parse_type": "日期时间",
                "use_separate_time_field": True,
                "input_structure": "自动识别常见格式",
                "output_mode": "生成多个字段",
                "new_field": "Stamp",
                "datetime_output_template": "{YYYY}-{MM}-{DD} {HH}:{mm}:{ss}",
                "component_prefix": "Part",
                "output_status": False,
            },
        )

        self.assertEqual(headers, ["Date", "Time", "Stamp", "Part年", "Part月", "Part日", "Part时", "Part分", "Part秒"])
        self.assertEqual(rows, [["2026-06-15", "09:08:07", "2026-06-15 09:08:07", "2026", "06", "15", "09", "08", "07"]])
        self.assertEqual(message, "格式规范化完成：写入 1 行，失败 0 行，跳过 0 行")

    def test_format_datetime_node_can_skip_failed_rows_when_overwriting(self):
        headers, rows, message = apply_format_datetime_node(
            ["Raw"],
            [["20260615"], ["not-a-date"]],
            {
                "source_field": "Raw",
                "parse_type": "日期",
                "input_structure": "自动识别常见格式",
                "output_mode": "覆盖源字段",
                "output_template": "{YY}{MM}{DD}",
                "output_status": True,
                "unmatched_mode": "跳过该行",
            },
        )

        self.assertEqual(headers, ["Raw", "格式解析状态"])
        self.assertEqual(rows, [["260615", "成功"], ["not-a-date", "跳过"]])
        self.assertEqual(message, "格式规范化完成：写入 1 行，失败 1 行，跳过 1 行")

    def test_parse_format_datetime_value_and_warning_helpers_are_pure(self):
        parts = parse_format_datetime_value(
            "２６／０６／１５",
            "",
            {
                "parse_type": "日期",
                "input_structure": "分隔符",
                "date_delimiter": "自动识别",
                "date_order": "年-月-日",
                "year_rule": "20xx",
            },
        )

        self.assertEqual(parts["year"], 2026)
        self.assertEqual(parts["month"], 6)
        self.assertEqual(parts["day"], 15)
        self.assertIn(
            "确认月日顺序",
            get_datetime_parse_warning(
                "03/06/26",
                {
                    "input_structure": "分隔符",
                    "date_delimiter": "自动识别",
                    "date_order": "月-日-年",
                    "year_rule": "20xx",
                },
                {"year": 2026, "month": 3, "day": 6},
            ),
        )

    def test_extract_node_regex_generates_unique_field_and_handles_unmatched(self):
        headers, rows, message = apply_extract_node(
            ["Text", "Code"],
            [["订单 A-001", ""], ["无编号", ""]],
            {
                "source_field": "Text",
                "method": "正则提取",
                "regex_pattern": r"([A-Z]-\d+)",
                "regex_group": "1",
                "new_field": "Code",
                "unmatched_mode": "填写固定值",
                "unmatched_fixed": "NA",
            },
        )

        self.assertEqual(headers, ["Text", "Code", "Code_2"])
        self.assertEqual(rows, [["订单 A-001", "", "A-001"], ["无编号", "", "NA"]])
        self.assertEqual(message, "写入 2 行，跳过 0 行")

    def test_extract_node_overwrites_source_and_skips_unmatched_rows(self):
        headers, rows, message = apply_extract_node(
            ["Text"],
            [["abc-123"], ["missing"]],
            {
                "source_field": "Text",
                "output_mode": "覆盖源字段",
                "method": "正则提取",
                "regex_pattern": r"(\d+)",
                "regex_group": "1",
                "unmatched_mode": "跳过该行",
            },
        )

        self.assertEqual(headers, ["Text"])
        self.assertEqual(rows, [["123"], ["missing"]])
        self.assertEqual(message, "写入 1 行，跳过 1 行")

    def test_extract_one_value_supports_regex_find_all_and_position_modes(self):
        value, status = extract_one_value(
            "a=1;b=22;c=333",
            {
                "method": "正则提取",
                "regex_pattern": r"=(\d+)",
                "regex_group": "1",
                "regex_find_all": True,
                "regex_joiner": "|",
            },
        )
        self.assertEqual((value, status), ("1|22|333", "成功"))

        self.assertEqual(
            extract_one_value(
                "abcdef",
                {"method": "固定位置提取", "start_pos": "2", "extract_len": "3", "position_base": "从1开始"},
            ),
            ("bcd", "成功"),
        )
        self.assertEqual(extract_one_value("abcdef", {"method": "从左取N位", "n_chars": "2"}), ("ab", "成功"))
        self.assertEqual(extract_one_value("abcdef", {"method": "从右取N位", "n_chars": "2"}), ("ef", "成功"))

    def test_extract_one_value_supports_delimiter_between_and_marker_modes(self):
        self.assertEqual(
            extract_one_value(
                "a--b--c",
                {"method": "按分隔符提取", "delimiter": "--", "part_index": "-1"},
            ),
            ("c", "成功"),
        )
        self.assertEqual(
            extract_one_value(
                "pre[one] mid [two]",
                {
                    "method": "前后关键字之间提取",
                    "before_key": "[",
                    "after_key": "]",
                    "between_occurrence": "2",
                },
            ),
            ("two", "成功"),
        )
        self.assertEqual(
            extract_one_value(
                "a-b-c",
                {"method": "指定字符前提取", "marker": "-", "find_mode": "最后一次出现"},
            ),
            ("a-b", "成功"),
        )
        self.assertEqual(
            extract_one_value(
                "a-b-c",
                {"method": "指定字符后提取", "marker": "-", "find_mode": "第一次出现"},
            ),
            ("b-c", "成功"),
        )

    def test_extract_one_value_supports_prefix_suffix_case_and_unmatched_modes(self):
        self.assertEqual(
            extract_one_value(
                "PRE-value",
                {"method": "删除前缀", "prefix": "pre-", "case_sensitive": False},
            ),
            ("value", "成功"),
        )
        self.assertEqual(
            extract_one_value(
                "value.TXT",
                {"method": "删除后缀", "suffix": ".txt", "case_sensitive": False},
            ),
            ("value", "成功"),
        )
        self.assertEqual(
            extract_one_value(
                "raw",
                {"method": "删除前缀", "prefix": "x", "unmatched_mode": "保留原值"},
            ),
            ("raw", "未匹配"),
        )
        self.assertEqual(
            extract_one_value(
                "raw",
                {"method": "固定位置提取", "start_pos": "99", "extract_len": "1", "unmatched_mode": "跳过该行"},
            ),
            ("", "跳过"),
        )


if __name__ == "__main__":
    unittest.main()
