# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for control-flow node execution wrappers."""

from workflow import group_runtime
from workflow import jump_runtime
from workflow import loop_node_runtime


class WorkflowControlNodeExecutionMixin:
    """Compatibility methods used by loop, group, and jump node runtime helpers."""

    def apply_loop_start_node(self, headers, rows, config, context=None):
        return loop_node_runtime.apply_loop_start_node_for_window(
            self,
            headers,
            rows,
            config,
            context=context,
        )

    def apply_loop_judge_node(self, headers, rows, config, context=None):
        return loop_node_runtime.apply_loop_judge_node_for_window(
            self,
            headers,
            rows,
            config,
            context=context,
        )

    def apply_group_node(self, headers, rows, config, execute_actions=False, context=None):
        return group_runtime.apply_group_node(
            self,
            headers,
            rows,
            config,
            execute_actions=execute_actions,
            context=context,
        )

    def apply_jump_anchor_node(self, headers, rows, config, context=None):
        return jump_runtime.apply_jump_anchor_node(self, headers, rows, config, context=context)

    def apply_unconditional_jump_node(self, headers, rows, config, context=None, anchors_info=None, nodes=None):
        return jump_runtime.apply_unconditional_jump_node(
            self,
            headers,
            rows,
            config,
            context=context,
            anchors_info=anchors_info,
            nodes=nodes,
        )

    def apply_condition_check_node(self, headers, rows, config, context=None):
        return jump_runtime.apply_condition_check_node(self, headers, rows, config, context=context)

    def apply_conditional_jump_node(self, headers, rows, config, context=None, anchors_info=None, nodes=None):
        return jump_runtime.apply_conditional_jump_node(
            self,
            headers,
            rows,
            config,
            context=context,
            anchors_info=anchors_info,
            nodes=nodes,
        )
