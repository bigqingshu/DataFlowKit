# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for output node runtime wrappers."""

from workflow import output_node_runtime as workflow_output_node_runtime


class WorkflowOutputRuntimeMixin:
    """Compatibility methods used by output, transit, and writeback runtime helpers."""

    def export_headers_rows_to_xlsx_file(self, headers, rows, path):
        return workflow_output_node_runtime.export_headers_rows_to_xlsx_file(
            self,
            headers,
            rows,
            path,
        )

    def apply_save_transit_memory_plan(self, context, memory_plan, headers_copy, rows_copy):
        return workflow_output_node_runtime.apply_save_transit_memory_plan(
            self,
            context,
            memory_plan,
            headers_copy,
            rows_copy,
        )

    def execute_save_transit_sqlite(self, options, headers_copy, rows_copy, context=None):
        return workflow_output_node_runtime.execute_save_transit_sqlite(
            self,
            options,
            headers_copy,
            rows_copy,
            context=context,
        )

    def execute_save_transit_xlsx(self, options, headers_copy, rows_copy):
        return workflow_output_node_runtime.execute_save_transit_xlsx(
            self,
            options,
            headers_copy,
            rows_copy,
        )

    def build_writeback_actions(self, headers, rows, config, context=None):
        return workflow_output_node_runtime.build_writeback_actions(
            self,
            headers,
            rows,
            config,
            context=context,
        )

    def apply_external_table_to_current_node(self, headers, rows, config, context=None):
        return workflow_output_node_runtime.apply_external_table_to_current_node_for_window(
            self,
            headers,
            rows,
            config,
            context=context,
        )
