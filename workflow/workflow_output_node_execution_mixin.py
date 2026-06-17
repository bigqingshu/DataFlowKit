# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for output node execution wrappers."""

from workflow import output_node_runtime


class WorkflowOutputNodeExecutionMixin:
    """Compatibility methods used by output, transit, selected-column, and writeback nodes."""

    def apply_selected_columns_write_node(self, headers, rows, config, context=None, execute_actions=False):
        return output_node_runtime.apply_selected_columns_write_node_for_window(
            self,
            headers,
            rows,
            config,
            context=context,
            execute_actions=execute_actions,
        )

    def apply_save_transit_node(self, headers, rows, config, context=None, execute_actions=False):
        return output_node_runtime.apply_save_transit_node_for_window(
            self,
            headers,
            rows,
            config,
            context=context,
            execute_actions=execute_actions,
        )

    def apply_writeback_node(self, headers, rows, config, execute_actions=False, context=None):
        return output_node_runtime.apply_writeback_node_for_window(
            self,
            headers,
            rows,
            config,
            execute_actions=execute_actions,
            context=context,
        )
