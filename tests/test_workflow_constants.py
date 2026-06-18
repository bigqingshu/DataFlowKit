# -*- coding: utf-8 -*-
import unittest

from workflow.workflow_constants import WorkflowConstantsMixin


class WorkflowConstantsTests(unittest.TestCase):
    def test_node_types_and_policy_choices_are_available(self):
        self.assertEqual(WorkflowConstantsMixin.NODE_TYPES[0], "获取文件列表")
        self.assertIn("插件节点", ["插件节点"])
        self.assertIn("循环判断回跳", WorkflowConstantsMixin.NODE_TYPES)
        self.assertEqual(WorkflowConstantsMixin.TABLE_ACCESS_POLICY_CHOICES, ["只审计", "预检确认", "强制拦截"])
        self.assertEqual(WorkflowConstantsMixin.TABLE_ACCESS_POLICY_DISPLAY["strict"], "强制拦截")

    def test_runtime_and_config_constants_keep_expected_values(self):
        self.assertEqual(WorkflowConstantsMixin.MAX_EXPANDED_ROWS, 200000)
        self.assertEqual(WorkflowConstantsMixin.MAX_TARGET_CELLS, 1000000)
        self.assertIn("正则匹配", WorkflowConstantsMixin.FILTER_OPS)
        self.assertIn("按匹配行号", WorkflowConstantsMixin.REPLACE_ROW_POLICIES)
        self.assertIn("timestamp_new", WorkflowConstantsMixin.STANDARD_WRITE_MODE_CHOICES)
        self.assertIn("自定义", WorkflowConstantsMixin.SEPARATOR_OPTIONS)


if __name__ == "__main__":
    unittest.main()
