# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for filter node execution wrappers."""

from workflow import filter_node_runtime


class WorkflowFilterNodeExecutionMixin:
    """Compatibility methods used by filter node runtime helpers."""

    def apply_filter_node(self, headers, rows, config, context=None):
        return filter_node_runtime.apply_filter_node_for_window(
            self,
            headers,
            rows,
            config,
            context=context,
        )
