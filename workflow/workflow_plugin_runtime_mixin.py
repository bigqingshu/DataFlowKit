# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for plugin input, IO, and runtime wrappers."""

from workflow import plugin_input_services as workflow_plugin_input_services
from workflow import plugin_io_services as workflow_plugin_io_services
from workflow import plugin_runtime_services as workflow_plugin_runtime_services
from workflow.nodes.plugin_nodes import (
    get_plugin_output_schema_table as workflow_get_plugin_output_schema_table,
    is_external_plugin_mode as workflow_is_external_plugin_mode,
    merge_plugin_output_fields_to_current as workflow_merge_plugin_output_fields_to_current,
    normalize_plugin_logs as workflow_normalize_plugin_logs,
    normalize_plugin_output_schema as workflow_normalize_plugin_output_schema,
    should_save_plugin_output_as_transit as workflow_should_save_plugin_output_as_transit,
)


class WorkflowPluginRuntimeMixin:
    """Compatibility methods used by plugin runtime service modules."""

    def read_plugin_input_table_source(self, spec, current_headers, current_rows, context=None):
        return workflow_plugin_input_services.read_plugin_input_table_source(
            self,
            spec,
            current_headers,
            current_rows,
            context=context,
        )

    def build_plugin_input_tables(self, config, current_headers, current_rows, context=None):
        return workflow_plugin_input_services.build_plugin_input_tables(
            self,
            config,
            current_headers,
            current_rows,
            context=context,
        )

    def read_plugin_input_table_headers(self, spec, current_headers, context=None):
        return workflow_plugin_input_services.read_plugin_input_table_headers(
            self,
            spec,
            current_headers,
            context=context,
        )

    def build_plugin_input_table_headers(self, config, current_headers, context=None):
        return workflow_plugin_input_services.build_plugin_input_table_headers(
            self,
            config,
            current_headers,
            context=context,
        )

    def normalize_plugin_logs(self, logs, plugin_id="", node_name="插件节点"):
        return workflow_normalize_plugin_logs(logs, plugin_id=plugin_id, node_name=node_name)

    def save_plugin_logs_to_file(self, plugin_id, log_items):
        return workflow_plugin_io_services.save_plugin_logs_to_file(self, plugin_id, log_items)

    def save_plugin_logs_to_sqlite(self, log_items, db_path=None, context=None):
        return workflow_plugin_io_services.save_plugin_logs_to_sqlite(
            self,
            log_items,
            db_path=db_path,
            context=context,
        )

    def plugin_log_items_to_table(self, log_items):
        return workflow_plugin_io_services.plugin_log_items_to_table(log_items)

    def save_plugin_output_to_transit(self, context, name, headers, rows, conflict_mode="覆盖", source="插件输出"):
        return workflow_plugin_io_services.save_plugin_output_to_transit(
            self,
            context,
            name,
            headers,
            rows,
            conflict_mode=conflict_mode,
            source=source,
        )

    def save_plugin_log_outputs(self, plugin_id, plugin_name, config, log_items, plugin_context=None, context=None, execute_actions=False, include_transit=True, suppress_errors=False):
        return workflow_plugin_io_services.save_plugin_log_outputs(
            self,
            plugin_id,
            plugin_name,
            config,
            log_items,
            plugin_context=plugin_context,
            context=context,
            execute_actions=execute_actions,
            include_transit=include_transit,
            suppress_errors=suppress_errors,
        )

    def save_plugin_result_transit_output(self, config, item, plugin_id, context, headers, rows, source_prefix="插件"):
        if not workflow_should_save_plugin_output_as_transit(config):
            return []
        name = config.get("transit_name") or item.get("info", {}).get("name", plugin_id)
        part = self.save_plugin_output_to_transit(
            context,
            name,
            headers,
            rows,
            config.get("transit_conflict_mode", "覆盖"),
            source=f"{source_prefix}:{plugin_id}",
        )
        return [part]

    def merge_plugin_output_fields_to_current(self, cur_headers, cur_rows, out_headers, out_rows):
        return workflow_merge_plugin_output_fields_to_current(cur_headers, cur_rows, out_headers, out_rows)

    def is_external_plugin_mode(self, config, item=None):
        return workflow_is_external_plugin_mode(config, item)

    def find_external_python(self, config, item=None, allow_current=False, return_info=False):
        return workflow_plugin_runtime_services.find_external_python(
            config,
            item=item,
            allow_current=allow_current,
            return_info=return_info,
        )

    def make_external_plugin_json_context(self, config, context=None, execute_actions=False):
        return workflow_plugin_runtime_services.make_external_plugin_json_context(
            self,
            config,
            context=context,
            execute_actions=execute_actions,
        )

    def run_external_plugin_process(self, item, input_data, params, config, context=None, execute_actions=False):
        return workflow_plugin_runtime_services.run_external_plugin_process(
            self,
            item,
            input_data,
            params,
            config,
            context=context,
            execute_actions=execute_actions,
        )

    def execute_external_plugin_database_requests(self, result, config, context=None, execute_actions=False):
        return workflow_plugin_runtime_services.execute_external_plugin_database_requests(
            self,
            result,
            config,
            context=context,
            execute_actions=execute_actions,
        )

    def make_plugin_context(self, config, context=None, execute_actions=False):
        return workflow_plugin_runtime_services.make_plugin_context(
            self,
            config,
            context=context,
            execute_actions=execute_actions,
        )

    def is_plugin_config_probe(self, context=None, execute_actions=False):
        """Configuration probes infer fields without running the plugin for real."""
        return bool((context or {}).get("is_config_probe")) and not bool(execute_actions)

    def build_plugin_probe_input_tables(self, config, current_headers, context=None):
        return workflow_plugin_input_services.build_plugin_probe_input_tables(
            self,
            config,
            current_headers,
            context=context,
        )

    def normalize_plugin_output_schema(self, schema, fallback_headers=None):
        return workflow_normalize_plugin_output_schema(schema, fallback_headers=fallback_headers)

    def get_plugin_output_schema_table(self, item, input_data, params, plugin_context, fallback_headers=None):
        return workflow_get_plugin_output_schema_table(item, input_data, params, plugin_context, fallback_headers=fallback_headers)
