# -*- coding: utf-8 -*-
"""Window adapters for advanced filter workflow node execution."""

from workflow.nodes.filter_execution_nodes import apply_filter_node as apply_filter_node_core
from workflow.nodes.filter_plan_nodes import (
    build_filter_config_probe_result,
    build_filter_runtime_plan,
)


def build_filter_node_context(window, headers, config, context=None):
    """Build the pure filter node context from window-managed table sources."""
    extra_tables = list(config.get("extra_tables", []))
    available_fields = (
        window.get_plan_filter_available_fields(headers, extra_tables, context)
        if extra_tables
        else None
    )
    runtime_plan = build_filter_runtime_plan(headers, config, available_fields=available_fields)

    if (context or {}).get("is_config_probe") and extra_tables:
        return runtime_plan, None

    table_records = {}
    for table in runtime_plan["extra_tables"]:
        table_records[table] = window.load_plan_table_records(
            table,
            context=context,
            required_fields=runtime_plan["table_required"].get(table),
        )

    node_context = {
        "lookup_fields": runtime_plan["lookup_fields"],
        "output_headers": runtime_plan["output_headers"],
        "current_required": runtime_plan["current_required"],
        "table_required": runtime_plan["table_required"],
        "table_records": table_records,
    }
    return runtime_plan, node_context


def apply_filter_node_for_window(window, headers, rows, config, context=None):
    """Run the advanced filter node using window-managed external table loading."""
    runtime_plan, node_context = build_filter_node_context(window, headers, config, context=context)
    if node_context is None:
        return build_filter_config_probe_result(runtime_plan["output_headers"])
    return apply_filter_node_core(headers, rows, runtime_plan["runtime_config"], context=node_context)
