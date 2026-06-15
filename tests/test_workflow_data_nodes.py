# -*- coding: utf-8 -*-
import unittest
import threading
from datetime import datetime

from workflow.nodes.data_nodes import (
    apply_area_fill_node,
    apply_copy_column_node,
    apply_copy_row_node,
    apply_current_datetime_column_node,
    apply_delete_columns_node,
    apply_delete_rows_node,
    apply_extract_node,
    apply_format_datetime_node,
    apply_fill_value_node,
    apply_move_columns_node,
    apply_new_columns_node,
    apply_replace_node,
    apply_sequence_fill_node,
    extract_one_value,
    get_datetime_parse_warning,
    parse_format_datetime_value,
    parse_new_columns_specs,
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
