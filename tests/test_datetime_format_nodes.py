# -*- coding: utf-8 -*-
import unittest

from workflow.nodes import data_nodes
from workflow.nodes.datetime_format_nodes import (
    apply_format_datetime_node,
    get_datetime_parse_warning,
    parse_format_datetime_value,
)


class DatetimeFormatNodesTests(unittest.TestCase):
    def test_data_nodes_keeps_datetime_format_compat_exports(self):
        self.assertIs(data_nodes.apply_format_datetime_node, apply_format_datetime_node)
        self.assertIs(data_nodes.parse_format_datetime_value, parse_format_datetime_value)
        self.assertIs(data_nodes.get_datetime_parse_warning, get_datetime_parse_warning)

    def test_parse_value_and_warning_helpers(self):
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

    def test_apply_format_datetime_node_outputs_components(self):
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


if __name__ == "__main__":
    unittest.main()
