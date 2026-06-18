# -*- coding: utf-8 -*-
import unittest

from workflow.nodes import data_nodes
from workflow.nodes.extract_nodes import (
    apply_extract_node,
    apply_unmatched_extract,
    extract_one_value,
    post_extract_result,
)


class ExtractNodesTests(unittest.TestCase):
    def test_data_nodes_keeps_extract_compat_exports(self):
        self.assertIs(data_nodes.apply_extract_node, apply_extract_node)
        self.assertIs(data_nodes.apply_unmatched_extract, apply_unmatched_extract)
        self.assertIs(data_nodes.extract_one_value, extract_one_value)
        self.assertIs(data_nodes.post_extract_result, post_extract_result)

    def test_apply_extract_node_generates_unique_field(self):
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

    def test_extract_one_value_modes(self):
        self.assertEqual(
            extract_one_value(
                "a=1;b=22;c=333",
                {
                    "method": "正则提取",
                    "regex_pattern": r"=(\d+)",
                    "regex_group": "1",
                    "regex_find_all": True,
                    "regex_joiner": "|",
                },
            ),
            ("1|22|333", "成功"),
        )
        self.assertEqual(
            extract_one_value("a--b--c", {"method": "按分隔符提取", "delimiter": "--", "part_index": "-1"}),
            ("c", "成功"),
        )
        self.assertEqual(
            extract_one_value("PRE-value", {"method": "删除前缀", "prefix": "pre-", "case_sensitive": False}),
            ("value", "成功"),
        )


if __name__ == "__main__":
    unittest.main()
