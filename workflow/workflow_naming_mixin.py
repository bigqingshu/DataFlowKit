# -*- coding: utf-8 -*-
"""Naming helpers for workflow windows."""

from datetime import datetime

from workflow.default_configs import default_name_for_node as get_default_name_for_node


class WorkflowNamingMixin:
    """Compatibility methods for workflow output and node names."""

    def make_default_output_table_name(self):
        base = self.app.sanitize_sql_name(self.app.table_name_var.get(), "计划结果")
        return f"{base}_计划结果_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def default_name_for_node(self, node_type):
        return get_default_name_for_node(node_type)
