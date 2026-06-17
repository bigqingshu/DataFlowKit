# -*- coding: utf-8 -*-
import os
import unittest

from workflow.default_configs import default_config_for_type


class DefaultConfigsTests(unittest.TestCase):
    def test_group_loop_and_jump_defaults_use_fixed_time(self):
        group = default_config_for_type("节点组 / 子工作流", ["A", "B"], now_text="123456")
        self.assertEqual(group["group_name"], "节点组_123456")
        self.assertEqual(group["input_source_type"], "当前工作表")
        self.assertEqual(group["transit_scope"], "组内中转私有")
        self.assertEqual(group["main_output_mode"], "输出为当前工作表")

        loop = default_config_for_type("循环执行起点", ["A", "B", "C", "D"], now_text="123456")
        self.assertEqual(loop["loop_id"], "loop_123456")
        self.assertEqual(loop["fields"], ["A", "B", "C"])
        self.assertEqual(loop["reference_field"], "A")

        anchor = default_config_for_type("跳转锚点节点", now_text="123456")
        self.assertEqual(anchor["anchor_id"], "anchor_123456")
        self.assertEqual(anchor["anchor_name"], "锚点_123456")

    def test_field_based_defaults_follow_preview_headers(self):
        replace = default_config_for_type("批量替换", ["Name", "Code"])
        self.assertEqual(replace["target_field"], "Name")
        self.assertEqual(replace["match_value_field"], "Name")

        merge = default_config_for_type("合并列", ["Name", "Code"])
        self.assertEqual(merge["fields"], ["Name", "Code"])
        self.assertEqual(merge["separators"], ["-"])

        numeric = default_config_for_type("列数字运算", ["Qty", "Price"])
        self.assertEqual(numeric["target_field"], "Qty")
        self.assertEqual(numeric["operand_field"], "Price")
        self.assertEqual(numeric["output_field"], "Qty_计算结果")

        empty_numeric = default_config_for_type("列数字运算", [])
        self.assertEqual(empty_numeric["output_field"], "计算结果")

    def test_table_dependent_defaults_use_injected_tables(self):
        config = default_config_for_type(
            "匹配值输出列名",
            ["Code"],
            table_names=["lookup"],
            table_columns={"lookup": ["K1", "K2", "K3", "K4"]},
        )
        self.assertEqual(config["lookup_table"], "lookup")
        self.assertEqual(config["lookup_fields"], ["K1", "K2", "K3"])

        selected = default_config_for_type("选定列写入指定表", ["A", "B", "C", "D"], table_names=["target"])
        self.assertEqual(selected["source_sqlite_table"], "target")
        self.assertEqual(selected["target_table"], "target")
        self.assertEqual(selected["selected_fields"], ["A", "B", "C"])

        writeback = default_config_for_type("字段映射写入表", table_names=["target"])
        self.assertEqual(writeback["target_table"], "target")
        self.assertEqual(writeback["source_table"], "target")

    def test_path_and_file_defaults_use_app_dir(self):
        app_dir = os.path.join("C:\\", "app")

        transit = default_config_for_type("保存中转数据", app_dir=app_dir, now_text="010203")
        self.assertEqual(transit["transit_name"], "中转_010203")
        self.assertEqual(transit["sqlite_table"], "中转_010203")
        self.assertEqual(transit["xlsx_path"], os.path.join(app_dir, "export", "中转_010203.xlsx"))

        file_list = default_config_for_type("获取文件列表", app_dir=app_dir)
        self.assertEqual(file_list["directory"], app_dir)
        self.assertTrue(file_list["recursive"])

        rename = default_config_for_type("批量重命名")
        self.assertEqual(rename["log_path"], os.path.abspath("rename_log.csv"))

    def test_unknown_node_returns_empty_config(self):
        self.assertEqual(default_config_for_type("不存在的节点", ["A"]), {})


if __name__ == "__main__":
    unittest.main()
