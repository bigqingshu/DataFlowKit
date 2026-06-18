# -*- coding: utf-8 -*-
import os
import tempfile
import unittest
from unittest.mock import patch

from DataFlowKit import PlanWorkflowWindow


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
        self.sanitize_calls = []

    def sanitize_sql_name(self, name, default_name):
        self.sanitize_calls.append((name, default_name))
        return f"safe_{name}"


class PluginRegistryMixinTests(unittest.TestCase):
    def make_window(self, app_dir):
        window = PlanWorkflowWindow.__new__(PlanWorkflowWindow)
        window.app = FakeApp(app_dir)
        window.NODE_TYPES = ["批量替换", "插件节点"]
        window.node_type_var = FakeVar("插件 / 演示")
        window.node_type_combo = FakeCombo()
        window.status_var = FakeVar("")
        window.plugin_registry = {}
        window.plugin_display_map = {}
        window.plugin_load_errors = []
        window.preview_headers = []
        window.rebuild_current_config = lambda: setattr(window, "rebuilt", True)
        window.get_plugins_dir = lambda: app_dir
        return window

    def test_load_plugins_refreshes_display_map_and_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            window = self.make_window(tmp)
            registry = {
                "p1": {"info": {"name": "演示"}, "load_status": "可内置运行", "schema": []},
                "p2": {"info": {"name": "演示"}, "load_status": "仅独立环境运行", "schema": []},
            }
            with patch("workflow.plugin_registry_mixin.scan_plugins", return_value=(registry, [{"file": "a", "error": "boom"}])):
                window.load_plugins(show_status=True)

        self.assertEqual(window.plugin_registry, registry)
        self.assertEqual(window.plugin_display_map["插件 / 演示"], "p1")
        self.assertEqual(window.plugin_display_map["插件 / 演示 [仅独立]"], "p2")
        self.assertIn("加载失败 1 个", window.status_var.get())

    def test_refresh_plugins_updates_combo_and_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            window = self.make_window(tmp)
            window.node_type_var.set("不存在")
            with patch.object(window, "load_plugins", side_effect=lambda show_status=False: setattr(window, "plugin_display_map", {"插件 / 演示": "p1"})):
                window.refresh_plugins()

        self.assertEqual(window.node_type_combo["values"], ["批量替换", "插件节点", "插件 / 演示"])
        self.assertEqual(window.node_type_var.get(), "批量替换")
        self.assertTrue(window.rebuilt)

    def test_default_config_for_plugin_uses_plugin_env_dir(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmp:
            window = self.make_window(tmp)
            window.plugin_registry = {
                "p1": {
                    "schema": [
                        {"name": "x", "default": 1},
                        {"name": "items", "type": "multi_field_select", "default": ""},
                    ],
                    "info": {"name": "演示", "run_mode": "external_python"},
                    "external_entry": "main.py",
                }
            }
            cfg = window.default_config_for_plugin("p1")

        self.assertEqual(cfg["run_mode"], "插件独立环境")
        self.assertEqual(cfg["external_env_dir"], os.path.join(tmp, "plugin_envs", "safe_p1"))
        self.assertEqual(cfg["params"], {"x": 1, "items": []})


if __name__ == "__main__":
    unittest.main()
