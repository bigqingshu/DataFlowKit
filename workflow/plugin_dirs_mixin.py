# -*- coding: utf-8 -*-
"""Plugin directory helpers for workflow windows."""

import os
import sys


def _default_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PluginDirsMixin:
    """Compatibility methods for plugin path helpers."""

    def get_plugins_dir(self):
        path = os.path.join(getattr(getattr(self, "app", None), "app_dir", _default_app_dir()), "plugins")
        os.makedirs(path, exist_ok=True)
        return path

    def get_plugin_data_dir(self, plugin_id=None):
        base = os.path.join(getattr(getattr(self, "app", None), "app_dir", _default_app_dir()), "plugin_data")
        if plugin_id:
            base = os.path.join(base, self.app.sanitize_sql_name(plugin_id, "plugin"))
        os.makedirs(base, exist_ok=True)
        return base

    def get_plugin_log_dir(self):
        path = os.path.join(getattr(getattr(self, "app", None), "app_dir", _default_app_dir()), "logs", "plugins")
        os.makedirs(path, exist_ok=True)
        return path

    def get_plugin_env_dir(self, plugin_id=None):
        base = os.path.join(getattr(getattr(self, "app", None), "app_dir", _default_app_dir()), "plugin_envs")
        if plugin_id:
            base = os.path.join(base, self.app.sanitize_sql_name(plugin_id, "plugin"))
        os.makedirs(base, exist_ok=True)
        return base
