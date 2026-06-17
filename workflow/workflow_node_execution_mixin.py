# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for node execution compatibility wrappers."""

from workflow.node_dispatch import apply_workflow_node
from workflow.workflow_control_node_execution_mixin import WorkflowControlNodeExecutionMixin
from workflow.workflow_filter_node_execution_mixin import WorkflowFilterNodeExecutionMixin
from workflow.workflow_output_node_execution_mixin import WorkflowOutputNodeExecutionMixin
from workflow.workflow_plugin_node_execution_mixin import WorkflowPluginNodeExecutionMixin


class WorkflowNodeExecutionMixin(
    WorkflowPluginNodeExecutionMixin,
    WorkflowControlNodeExecutionMixin,
    WorkflowOutputNodeExecutionMixin,
    WorkflowFilterNodeExecutionMixin,
):
    """Compatibility methods used by node dispatch and runtime helpers."""

    def apply_node(self, headers, rows, node, execute_actions=False, context=None):
        return apply_workflow_node(
            self,
            headers,
            rows,
            node,
            execute_actions=execute_actions,
            context=context,
        )
