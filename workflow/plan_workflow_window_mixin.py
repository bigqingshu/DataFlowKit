# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for main workflow UI wrappers."""

from workflow import plan_workflow_ui


class PlanWorkflowUiMixin:
    """Compatibility methods used by the main workflow UI module."""

    def build_ui(self):
        return plan_workflow_ui.build_ui(self)

    def build_node_config(self, idx):
        return plan_workflow_ui.build_node_config(self, idx)

    def on_preview_tree_double_click(self, event):
        return plan_workflow_ui.on_preview_tree_double_click(self, event)

    def refresh_plan_template_list(self, show_status=True):
        return plan_workflow_ui.refresh_plan_template_list(self, show_status=show_status)
