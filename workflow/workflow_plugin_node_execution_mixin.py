# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for plugin node execution wrappers."""

from workflow import plugin_node_runtime


class WorkflowPluginNodeExecutionMixin:
    """Compatibility methods used by plugin node runtime helpers."""

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
