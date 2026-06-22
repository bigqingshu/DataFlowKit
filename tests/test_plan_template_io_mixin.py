# -*- coding: utf-8 -*-
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from workflow.plan_template_io_mixin import PlanTemplateIoMixin


class FakeVar:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeCombo(dict):
    pass


class FakeApp:
    def __init__(self, app_dir):
        self.app_dir = app_dir


class FakePlanWindow(PlanTemplateIoMixin):
    def __init__(self, app_dir):
        self.app = FakeApp(app_dir)
        self.nodes = [{"type": "批量替换", "name": "替换", "config": {}}]
        self.output_mode_var = FakeVar("保存为SQLite新表")
        self.output_table_var = FakeVar("默认输出表")
        self.backup_before_overwrite_var = FakeVar(False)
        self.status_var = FakeVar("")
        self.plan_template_var = FakeVar("")
        self.plan_template_map = {}
        self.plan_template_combo = FakeCombo()
        self.window = None
        self.plan_dir = self.get_plan_dir()
        self.refreshed_access = False
        self.ensured_identity = False
        self.refreshed_list = False
        self.rebuilt_config = False
        self.policy_value = None

    def refresh_node_tree_table_access(self, nodes):
        self.refreshed_access = True
        for index, node in enumerate(nodes, start=1):
            node.setdefault("node_id", f"node_{index}")
            node.setdefault("table_access", {"version": 1, "tables": []})

    def normalize_table_access_policy(self):
        return "prompt"

    def ensure_node_tree_identity(self, nodes):
        self.ensured_identity = True
        for index, node in enumerate(nodes, start=1):
            node.setdefault("node_id", f"node_{index}")

    def ensure_node_identity(self, node):
        node.setdefault("node_id", "node_1")

    def make_default_output_table_name(self):
        return "默认计划结果"

    def set_table_access_policy(self, value):
        self.policy_value = value

    def refresh_node_list(self):
        self.refreshed_list = True

    def rebuild_current_config(self):
        self.rebuilt_config = True

    def refresh_plan_template_list(self, show_status=True):
        self.plan_template_map = dict(getattr(self, "next_template_map", {}))


class PlanTemplateIoMixinTests(unittest.TestCase):
    def test_build_and_validate_plan_template_data(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmp:
            window = FakePlanWindow(tmp)
            data = window.build_plan_template_data()

        self.assertTrue(window.refreshed_access)
        self.assertEqual(data["template_type"], "workflow_plan")
        self.assertEqual(data["plan_name"], "默认输出表")
        self.assertEqual(data["table_access_policy"], "prompt")
        self.assertEqual(data["nodes"][0]["node_type_id"], "core.replace")
        self.assertEqual(data["nodes"][0]["node_version"], "1.0.0")
        self.assertNotIn("node_type_id", window.nodes[0])
        self.assertEqual(window.validate_plan_template_data(data), (True, ""))
        self.assertEqual(window.validate_plan_template_data({"template_type": "old"}), (False, "template_type 不是 workflow_plan。"))

    def test_apply_plan_template_data_updates_window_state(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmp:
            window = FakePlanWindow(tmp)
            window.apply_plan_template_data(
                {
                    "template_type": "workflow_plan",
                    "nodes": [{"type": "数据提取", "name": "提取", "config": {}}],
                    "output_mode": "输出到主界面预览区",
                    "output_table": "结果表",
                    "backup_before_overwrite": True,
                    "table_access_policy": "strict",
                },
                source_path="demo.json",
            )

        self.assertEqual(window.nodes[0]["type"], "数据提取")
        self.assertTrue(window.ensured_identity)
        self.assertTrue(window.refreshed_list)
        self.assertTrue(window.rebuilt_config)
        self.assertEqual(window.output_table_var.get(), "结果表")
        self.assertEqual(window.policy_value, "strict")
        self.assertIn("demo.json", window.status_var.get())

    def test_save_plan_template_uses_saved_file_name_as_plan_name(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmp:
            window = FakePlanWindow(tmp)
            path = os.path.join(window.plan_dir, "PDF批量重命名.json")
            window.next_template_map = {"PDF批量重命名": path}

            with patch("workflow.plan_template_io_mixin.filedialog.asksaveasfilename", return_value=path):
                window.save_plan_template()

            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

        self.assertEqual(data["plan_name"], "PDF批量重命名")
        self.assertEqual(data["output_table"], "默认输出表")
        self.assertEqual(window.plan_template_var.get(), "PDF批量重命名")
        self.assertIn("plan_name 已同步", window.status_var.get())

    def test_sanitize_plan_file_name_replaces_invalid_characters(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmp:
            window = FakePlanWindow(tmp)

        self.assertEqual(window.sanitize_plan_file_name('A/B:C*D?"E<>F|G'), "A_B_C_D_E_F_G")
        self.assertEqual(window.sanitize_plan_file_name(""), "工作流计划")


if __name__ == "__main__":
    unittest.main()
