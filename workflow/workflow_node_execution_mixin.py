# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for node execution compatibility wrappers."""

from workflow import filter_node_runtime
from workflow import group_runtime
from workflow import jump_runtime
from workflow import loop_node_runtime
from workflow import node_dispatch
from workflow import output_node_runtime
from workflow import plugin_node_runtime


class WorkflowNodeExecutionMixin:
    """Compatibility methods used by node dispatch and runtime helpers."""

    def apply_lazy_plugin_probe_node(self, headers, rows, config, item, params, runtime_context):
        return plugin_node_runtime.apply_lazy_plugin_probe_node_for_window(
            self,
            headers,
            rows,
            config,
            item,
            params,
            runtime_context,
        )

    def run_plugin_node_runtime(self, headers, rows, config, item, params, runtime_context, execute_actions=False):
        return plugin_node_runtime.run_plugin_node_runtime_for_window(
            self,
            headers,
            rows,
            config,
            item,
            params,
            runtime_context,
            execute_actions=execute_actions,
        )

    def apply_plugin_node(self, headers, rows, config, context=None, execute_actions=False):
        return plugin_node_runtime.apply_plugin_node_for_window(
            self,
            headers,
            rows,
            config,
            context=context,
            execute_actions=execute_actions,
        )

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

    def apply_selected_columns_write_node(self, headers, rows, config, context=None, execute_actions=False):
        return output_node_runtime.apply_selected_columns_write_node_for_window(
            self,
            headers,
            rows,
            config,
            context=context,
            execute_actions=execute_actions,
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

    def apply_node(self, headers, rows, node, execute_actions=False, context=None):
        return node_dispatch.apply_workflow_node(
            self,
            headers,
            rows,
            node,
            execute_actions=execute_actions,
            context=context,
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

    def apply_filter_node(self, headers, rows, config, context=None):
        return filter_node_runtime.apply_filter_node_for_window(
            self,
            headers,
            rows,
            config,
            context=context,
        )
