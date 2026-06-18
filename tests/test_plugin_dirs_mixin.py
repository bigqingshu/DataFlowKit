# -*- coding: utf-8 -*-
import os
import tempfile
import unittest

from core.text_utils import sanitize_sql_name
from workflow.plugin_dirs_mixin import PluginDirsMixin


class FakeApp:
    def __init__(self, app_dir):
        self.app_dir = app_dir

    def sanitize_sql_name(self, name, default_name):
        return sanitize_sql_name(name, default_name)


class FakePluginWindow(PluginDirsMixin):
    def __init__(self, app_dir):
        self.app = FakeApp(app_dir)


class PluginDirsMixinTests(unittest.TestCase):
    def test_plugin_directories_are_created_under_app_dir(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmp:
            window = FakePluginWindow(tmp)

            plugins_dir = window.get_plugins_dir()
            data_dir = window.get_plugin_data_dir("插件 / A:B")
            log_dir = window.get_plugin_log_dir()
            env_dir = window.get_plugin_env_dir("插件 / A:B")

            self.assertEqual(plugins_dir, os.path.join(tmp, "plugins"))
            self.assertEqual(data_dir, os.path.join(tmp, "plugin_data", "插件_A_B"))
            self.assertEqual(log_dir, os.path.join(tmp, "logs", "plugins"))
            self.assertEqual(env_dir, os.path.join(tmp, "plugin_envs", "插件_A_B"))
            for path in (plugins_dir, data_dir, log_dir, env_dir):
                self.assertTrue(os.path.isdir(path), path)


if __name__ == "__main__":
    unittest.main()
