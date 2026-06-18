# -*- coding: utf-8 -*-
"""Compatibility wrappers for workflow group template actions."""

import os
import sys
from tkinter import filedialog, messagebox, simpledialog

from shared.atomic_json_utils import atomic_write_json, load_json_with_backup
from workflow import group_template_ui


def _default_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_json_file_with_recovery(path, parent=None):
    data, info = load_json_with_backup(path)
    warning = info.get("warning", "")
    if warning:
        messagebox.showwarning("配置已从备份恢复", warning, parent=parent)
    return data


class WorkflowGroupTemplateMixin:
    """PlanWorkflowWindow group/subworkflow template methods."""

    def merge_selected_nodes_to_group(self):
        return group_template_ui.merge_selected_nodes_to_group(
            self,
            messagebox_module=messagebox,
            simpledialog_module=simpledialog,
        )

    def expand_selected_group(self):
        return group_template_ui.expand_selected_group(self, messagebox_module=messagebox)

    def get_group_dir(self):
        return group_template_ui.get_group_dir(self, _default_app_dir)

    def validate_group_template_data(self, data):
        return group_template_ui.validate_group_template_data(data)

    def build_group_template_data(self, config, group_name=None):
        return group_template_ui.build_group_template_data(config, group_name=group_name)

    def group_config_from_template_data(self, data):
        return group_template_ui.group_config_from_template_data(data)

    def save_group_template_from_config(self, config):
        return group_template_ui.save_group_template_from_config(
            self,
            config,
            atomic_write_json,
            messagebox_module=messagebox,
            filedialog_module=filedialog,
        )

    def load_group_template_dialog(self):
        return group_template_ui.load_group_template_dialog(
            self,
            _load_json_file_with_recovery,
            messagebox_module=messagebox,
            filedialog_module=filedialog,
        )

    def open_group_dir(self):
        return group_template_ui.open_group_dir(self, messagebox_module=messagebox)
