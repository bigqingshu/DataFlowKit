# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for loop, group, and jump runtime wrappers."""

from workflow import group_runtime as workflow_group_runtime
from workflow import jump_runtime as workflow_jump_runtime
from workflow import loop_node_runtime as workflow_loop_node_runtime


class WorkflowControlRuntimeMixin:
    """Compatibility methods used by control-flow runtime modules."""

    def get_loop_source_table_data(self, headers, rows, config, context=None):
        return workflow_loop_node_runtime.get_loop_source_table_data(
            self,
            headers,
            rows,
            config,
            context=context,
        )

    def init_loop_state(self, headers, rows, config, context=None):
        return workflow_loop_node_runtime.init_loop_state_for_window(
            self,
            headers,
            rows,
            config,
            context=context,
        )

    def get_group_source_table_data(self, headers, rows, config, context=None):
        return workflow_group_runtime.get_group_source_table_data(
            self,
            headers,
            rows,
            config,
            context=context,
        )

    def write_group_outputs(self, result_headers, result_rows, config, parent_context, execute_actions=False):
        return workflow_group_runtime.write_group_outputs(
            self,
            result_headers,
            result_rows,
            config,
            parent_context,
            execute_actions=execute_actions,
        )

    def prepare_group_inner_node_execution(self, child_context, node, node_type, node_index, cur_headers):
        return workflow_group_runtime.prepare_group_inner_node_execution(
            self,
            child_context,
            node,
            node_type,
            node_index,
            cur_headers,
        )

    def run_group_inner_nodes(self, cur_headers, cur_rows, nodes, child_context, execute_actions=False):
        return workflow_group_runtime.run_group_inner_nodes(
            self,
            cur_headers,
            cur_rows,
            nodes,
            child_context,
            execute_actions=execute_actions,
        )

    def append_jump_runtime_log(self, context, event):
        return workflow_jump_runtime.append_jump_runtime_log(context, event)

    def resolve_jump_target_control(self, anchor_id, context=None, anchors_info=None, nodes=None, source="跳转"):
        return workflow_jump_runtime.resolve_jump_target_control(
            self,
            anchor_id,
            context=context,
            anchors_info=anchors_info,
            nodes=nodes,
            source=source,
        )

    def condition_count_empty_cells(self, headers, rows, field):
        return workflow_jump_runtime.condition_count_empty_cells(self, headers, rows, field)

    def condition_count_contains_cells(self, headers, rows, field, value, case_sensitive=True):
        return workflow_jump_runtime.condition_count_contains_cells(
            self,
            headers,
            rows,
            field,
            value,
            case_sensitive=case_sensitive,
        )

    def evaluate_condition_check_node(self, headers, rows, config, context=None):
        return workflow_jump_runtime.evaluate_condition_check_node(
            self,
            headers,
            rows,
            config,
            context=context,
        )

    def find_conditional_jump_target(self, flag_value, config):
        return workflow_jump_runtime.find_conditional_jump_target(flag_value, config)
