# -*- coding: utf-8 -*-
"""Window adapters for plugin workflow node execution."""

import copy
import traceback

from workflow.nodes.plugin_nodes import (
    build_plugin_failure_output,
    build_plugin_final_output,
    build_plugin_probe_final_output,
    build_plugin_probe_stat,
    build_plugin_status_text,
    make_plugin_input_data,
    normalize_plugin_run_result,
)


def apply_lazy_plugin_probe_node_for_window(window, headers, rows, config, item, params, runtime_context):
    """Return declared plugin fields during config probing without running the plugin."""
    plugin_id = config.get("plugin_id", "")
    input_tables = window.build_plugin_probe_input_tables(config, headers, runtime_context)
    runtime_context["input_tables"] = input_tables
    runtime_context["plugin_input_table_specs"] = copy.deepcopy(config.get("input_tables", []))
    input_data = make_plugin_input_data(plugin_id, headers, [], input_tables, lazy_schema=True)
    plugin_context = window.make_plugin_context(config, runtime_context, execute_actions=False)
    schema_table = window.get_plugin_output_schema_table(item, input_data, params, plugin_context, fallback_headers=headers)
    schema_declared = schema_table is not None
    if schema_table is None:
        schema_table = {
            "type": "table",
            "headers": list(headers),
            "rows": [list(r) for r in rows],
            "meta": {"lazy_schema": True, "schema_fallback": "pass_through"},
        }

    new_headers = list(schema_table.get("headers", headers))
    new_rows = [list(r) for r in schema_table.get("rows", [])]
    output_mode = config.get("output_mode", "使用插件返回结果")
    transit_parts = window.save_plugin_result_transit_output(
        config,
        item,
        plugin_id,
        runtime_context,
        new_headers,
        new_rows,
        source_prefix="插件字段探测",
    )

    final_headers, final_rows = build_plugin_probe_final_output(
        headers,
        rows,
        new_headers,
        new_rows,
        output_mode,
        schema_declared,
    )

    plugin_name = item.get("info", {}).get("name", plugin_id)
    stat = build_plugin_probe_stat(plugin_name, schema_declared, final_headers, transit_parts)
    return final_headers, final_rows, stat


def run_plugin_node_runtime_for_window(window, headers, rows, config, item, params, runtime_context, execute_actions=False):
    """Build plugin input/context, dispatch internal or external plugin, and normalize its output."""
    plugin_id = config.get("plugin_id", "")
    input_tables = window.build_plugin_input_tables(config, headers, rows, runtime_context)
    runtime_context["input_tables"] = input_tables
    runtime_context["plugin_input_table_specs"] = copy.deepcopy(config.get("input_tables", []))
    input_data = make_plugin_input_data(plugin_id, headers, rows, input_tables)
    plugin_context = window.make_plugin_context(config, runtime_context, execute_actions=execute_actions)

    if window.is_external_plugin_mode(config, item):
        result = window.run_external_plugin_process(
            item,
            input_data,
            params,
            config,
            runtime_context,
            execute_actions=execute_actions,
        )
    else:
        module = item.get("module")
        if module is None:
            raise RuntimeError("该插件未在主程序环境中导入。请将运行环境设置为“插件独立环境”，或改用单文件内置插件。")
        validate = getattr(module, "validate_params", None)
        if callable(validate):
            ok_msg = validate(params, input_data, plugin_context)
            if isinstance(ok_msg, tuple):
                ok, msg = ok_msg
                if not ok:
                    raise ValueError(msg or "插件参数校验失败")
            elif ok_msg is False:
                raise ValueError("插件参数校验失败")
        result = module.run(input_data, params, plugin_context)

    normalized_result = normalize_plugin_run_result(result, input_data, headers, rows)
    return normalized_result, plugin_context, input_data


def apply_plugin_node_for_window(window, headers, rows, config, context=None, execute_actions=False):
    """Run a plugin workflow node and apply output/log/failure policies."""
    plugin_id = config.get("plugin_id", "")
    item = window.plugin_registry.get(plugin_id)
    if not item:
        raise ValueError(f"插件未加载或缺失：{plugin_id}")
    params = dict(config.get("params", {}))
    runtime_context = dict(context or {})
    if isinstance(context, dict):
        runtime_context["table_access_logs"] = context.setdefault("table_access_logs", [])
    if window.is_plugin_config_probe(runtime_context, execute_actions=execute_actions):
        return apply_lazy_plugin_probe_node_for_window(window, headers, rows, config, item, params, runtime_context)
    plugin_context = None
    failure_policy = config.get("plugin_failure_policy", "停止工作流")

    try:
        normalized_result, plugin_context, _input_data = run_plugin_node_runtime_for_window(
            window,
            headers,
            rows,
            config,
            item,
            params,
            runtime_context,
            execute_actions=execute_actions,
        )
        message = normalized_result["message"]
        logs = normalized_result["logs"]
        summary = normalized_result["summary"]
        new_headers = normalized_result["headers"]
        new_rows = normalized_result["rows"]
        ok = True
    except Exception as e:
        ok = False
        error_message = str(e)
        logs = [{"level": "ERROR", "message": error_message, "traceback": traceback.format_exc()}]
        message = error_message
        summary = {"ok": False, "error": error_message}
        new_headers = list(headers)
        new_rows = [list(r) for r in rows]
        if failure_policy == "停止工作流":
            log_items = window.normalize_plugin_logs(logs, plugin_id=plugin_id, node_name=config.get("name") or "插件节点")
            window.save_plugin_log_outputs(
                plugin_id,
                item.get("info", {}).get("name", plugin_id),
                config,
                log_items,
                plugin_context=plugin_context,
                context=runtime_context,
                execute_actions=execute_actions,
                include_transit=False,
                suppress_errors=True,
            )
            raise
        new_headers, new_rows = build_plugin_failure_output(
            plugin_id,
            error_message,
            traceback.format_exc(),
            headers,
            rows,
            failure_policy,
        )

    log_items = window.normalize_plugin_logs(logs, plugin_id=plugin_id, node_name=config.get("name") or "插件节点")
    plugin_name = item.get("info", {}).get("name", plugin_id)
    log_saved_parts = window.save_plugin_log_outputs(
        plugin_id,
        plugin_name,
        config,
        log_items,
        plugin_context=plugin_context,
        context=context,
        execute_actions=execute_actions,
    )

    output_mode = config.get("output_mode", "使用插件返回结果")
    transit_parts = window.save_plugin_result_transit_output(config, item, plugin_id, context, new_headers, new_rows)

    final_headers, final_rows = build_plugin_final_output(
        headers,
        rows,
        new_headers,
        new_rows,
        output_mode,
    )
    stat = build_plugin_status_text(
        plugin_name,
        plugin_id,
        ok,
        failure_policy,
        message,
        summary,
        transit_parts,
        log_saved_parts,
        log_items,
    )
    return final_headers, final_rows, stat
