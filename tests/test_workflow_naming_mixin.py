# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from workflow.workflow_naming_mixin import WorkflowNamingMixin


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value


class FakeApp:
    def __init__(self):
        self.table_name_var = FakeVar("原始 表")

    def sanitize_sql_name(self, value, fallback):
        return value.replace(" ", "_") if value else fallback


class FakeWindow(WorkflowNamingMixin):
    def __init__(self):
        self.app = FakeApp()


class WorkflowNamingMixinTests(unittest.TestCase):
    def test_make_default_output_table_name_uses_sanitized_base_and_timestamp(self):
        window = FakeWindow()

        with patch("workflow.workflow_naming_mixin.datetime") as fake_datetime:
            fake_datetime.now.return_value.strftime.return_value = "20260618_123456"
            self.assertEqual(
                window.make_default_output_table_name(),
                "原始_表_计划结果_20260618_123456",
            )

    def test_default_name_for_node_delegates_to_default_config_names(self):
        window = FakeWindow()

        self.assertEqual(window.default_name_for_node("高级筛选"), "筛选数据")
        self.assertEqual(window.default_name_for_node("未知节点"), "未知节点")


if __name__ == "__main__":
    unittest.main()
