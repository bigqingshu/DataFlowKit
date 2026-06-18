# -*- coding: utf-8 -*-
import unittest

from workflow.workflow_headless_adapter_mixin import WorkflowHeadlessAdapterMixin
from workflow.workflow_task_snapshot_mixin import WorkflowTaskSnapshotMixin


class FakeVar:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value


class FakeApp:
    headers = ["A"]
    rows = [["a"]]


class FakeWindow(WorkflowHeadlessAdapterMixin, WorkflowTaskSnapshotMixin):
    def __init__(self):
        self.app = FakeApp()
        self.nodes = [
            {
                "type": "新建列",
                "enabled": True,
                "config": {"columns_text": "B=b", "value_mode": "按列配置值"},
            }
        ]
        self.output_table_var = FakeVar("结果")
        self.output_mode_var = FakeVar("输出到主界面预览区")
        self.backup_before_overwrite_var = FakeVar(True)

    def normalize_table_access_policy(self):
        return "audit"

    def ensure_node_identity(self, node):
        node.setdefault("node_id", "node_1")


class WorkflowHeadlessAdapterMixinTests(unittest.TestCase):
    def test_build_headless_runtime_request_uses_protocol_payload(self):
        window = FakeWindow()

        request = window.build_headless_runtime_request("preview_plan", request_id="r1", stop_index=0)

        self.assertEqual(request["request_id"], "r1")
        self.assertEqual(request["api_version"], "1.0")
        self.assertEqual(request["action"], "preview_plan")
        self.assertEqual(request["payload"]["stop_at"], 0)
        self.assertEqual(request["payload"]["input_data"]["headers"], ["A"])
        self.assertEqual(request["payload"]["plan"]["nodes"][0]["node_type_id"], "core.new_columns")

    def test_validate_and_preview_current_plan_headless(self):
        window = FakeWindow()

        validation = window.validate_current_plan_for_headless()
        result = window.preview_current_plan_headless()

        self.assertTrue(validation["ok"])
        self.assertEqual(result.headers, ["A", "B"])
        self.assertEqual(result.rows, [["a", "b"]])


if __name__ == "__main__":
    unittest.main()
