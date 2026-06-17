# -*- coding: utf-8 -*-
"""Runtime orchestration for group/subworkflow nodes."""

import copy

from workflow.nodes.group_nodes import (
    build_empty_group_stat,
    build_group_final_output,
    build_group_node_log,
    build_group_status_text,
    ensure_group_parent_context,
    merge_group_child_audit_logs,
)


def get_group_source_table_data(window, headers, rows, config, context=None):
    """读取节点组入口数据源：当前工作表 / 中转副表 / SQLite表。"""
    source_type = config.get("input_source_type", "当前工作表")
    if source_type == "当前工作表":
        return list(headers), [list(r) for r in rows], "当前工作表"
    if source_type == "中转副表":
        name = str(config.get("input_transit_table", "")).strip()
        if not name:
            raise ValueError("节点组入口选择了中转副表，但没有填写中转副表名。")
        manager = window.check_transit_table_permission(
            context,
            name,
            ["read_table"],
            operation="read_transit_table",
            field_action="read",
            node_type="节点组 / 子工作流",
        )
        tables = (context or {}).get("transit_tables", {})
        if name not in tables:
            raise ValueError(f"节点组入口未找到中转副表：{name}")
        item = tables.get(name, {}) or {}
        source_headers = list(item.get("headers", []))
        source_rows = [list(r) for r in item.get("rows", [])]
        window.log_transit_table_event(manager, "read_transit_table", name, source_headers, source_rows, message=f"节点组入口读取中转副表 {name}：{len(source_rows)} 行 × {len(source_headers)} 列")
        return source_headers, source_rows, f"中转副表:{name}"
    if source_type == "SQLite表":
        name = str(config.get("input_sqlite_table", "")).strip()
        if not name:
            raise ValueError("节点组入口选择了 SQLite 表，但没有填写表名。")
        db = window.get_table_manager(context if isinstance(context, dict) else None, node_type="节点组 / 子工作流")
        data = db.read_table(name)
        return list(data.get("headers", [])), [list(r) for r in data.get("rows", [])], f"SQLite:{name}"
    return list(headers), [list(r) for r in rows], "当前工作表"


def write_group_outputs(window, result_headers, result_rows, config, parent_context, execute_actions=False):
    """根据节点组输出设置，把结果保存到中转副表或 SQLite。返回状态文本列表。"""
    parts = []
    parent_context = parent_context if parent_context is not None else {"transit_tables": {}, "loop_states": {}, "loop_results": {}}
    parent_context.setdefault("transit_tables", {})

    if config.get("save_to_transit", False):
        name = str(config.get("output_transit_name") or config.get("group_name") or "节点组结果").strip() or "节点组结果"
        conflict = window.normalize_group_transit_conflict_mode(config.get("output_transit_conflict_mode", "覆盖整表"))
        parts.append(window.save_plugin_output_to_transit(parent_context, name, result_headers, result_rows, conflict, source=f"节点组:{config.get('group_name','节点组')}"))

    sqlite_preview_only = bool((parent_context or {}).get("selected_columns_config_preview_only", False))
    allow_sqlite = bool(config.get("save_to_sqlite", False)) and (execute_actions or bool(config.get("sqlite_save_in_preview", False))) and not sqlite_preview_only
    if config.get("save_to_sqlite", False) and not allow_sqlite:
        parts.append("SQLite保存已跳过：仅执行计划时保存")
    elif allow_sqlite:
        table_name = str(config.get("output_sqlite_table") or config.get("group_name") or "节点组结果").strip()
        if not table_name:
            raise ValueError("节点组已启用 SQLite 输出，但未填写 SQLite 表名。")
        mode = window.normalize_group_sqlite_mode(config.get("output_sqlite_mode", "自动加时间戳新表"))
        db = window.get_table_manager(parent_context, node_type="节点组 / 子工作流")
        info = db.write_table(table_name, result_headers, result_rows, mode=mode)
        parts.append(f"SQLite表：{info.get('table_name')}（{info.get('rows')}行）")
        requests = parent_context.setdefault("ui_refresh_requests", [])
        if "table_list" not in requests:
            requests.append("table_list")
    return parts


def prepare_group_inner_node_execution(window, child_context, node, node_type, node_index, cur_headers):
    window.ensure_node_identity(node)
    window.refresh_node_table_access(node)
    child_context["current_node_info"] = {
        "node_id": node.get("node_id", ""),
        "node_name": node.get("name", ""),
        "node_type": node_type,
        "node_index": node_index,
        "table_access": copy.deepcopy(node.get("table_access", {})),
    }
    if node_type in ("循环执行起点", "循环判断回跳"):
        raise ValueError("第一版节点组暂不支持组内循环执行起点 / 循环判断回跳。")
    if node_type in ("跳转锚点节点", "无条件跳转节点", "条件跳转节点"):
        return window.get_table_manager(child_context, node_type=node_type)
    manager = window.check_current_table_permission(
        child_context,
        cur_headers,
        write=False,
        operation="read_current_table",
    )
    if node_type != "条件判断节点":
        manager = window.check_current_table_permission(
            child_context,
            cur_headers,
            write=True,
            operation="write_current_table",
        )
    return manager


def run_group_inner_nodes(window, cur_headers, cur_rows, nodes, child_context, execute_actions=False):
    logs = []
    for i, node in enumerate(nodes):
        if not node.get("enabled", True):
            logs.append(f"{i+1}.{node.get('type')} 已禁用")
            continue
        node_type = node.get("type")
        before_shape = (len(cur_rows), len(cur_headers))
        current_table_manager = window.prepare_group_inner_node_execution(
            child_context,
            node,
            node_type,
            i,
            cur_headers,
        )
        cur_headers, cur_rows, stat = window.apply_node(
            cur_headers,
            cur_rows,
            node,
            execute_actions=execute_actions,
            context=child_context,
        )
        window.log_current_table_transform(
            current_table_manager,
            before_shape,
            cur_headers,
            cur_rows,
            node_type=node_type,
        )
        after_shape = (len(cur_rows), len(cur_headers))
        logs.append(build_group_node_log(i + 1, node_type, before_shape, after_shape, stat))
    return cur_headers, cur_rows, logs


def apply_group_node(window, headers, rows, config, execute_actions=False, context=None):
    nodes = config.get("nodes", [])
    group_name = config.get("group_name") or "节点组"

    context = ensure_group_parent_context(context)

    source_headers, source_rows, source_name = window.get_group_source_table_data(headers, rows, config, context=context)
    cur_headers, cur_rows, input_stat = window.build_group_input_table(source_headers, source_rows, config)

    if not nodes:
        output_parts = window.write_group_outputs(cur_headers, cur_rows, config, context, execute_actions=execute_actions)
        if config.get("main_output_mode", "输出为当前工作表") == "透传原当前表":
            stat = build_empty_group_stat(group_name, source_name, input_stat, output_parts, passthrough_current=True)
            return list(headers), [list(r) for r in rows], stat
        stat = build_empty_group_stat(group_name, source_name, input_stat, output_parts)
        return cur_headers, cur_rows, stat

    child_context = window.make_group_child_context(context, config)

    def merge_child_audit_logs():
        merge_group_child_audit_logs(context, child_context)

    try:
        cur_headers, cur_rows, logs = window.run_group_inner_nodes(
            cur_headers,
            cur_rows,
            nodes,
            child_context,
            execute_actions=execute_actions,
        )
    except Exception:
        merge_child_audit_logs()
        raise
    merge_child_audit_logs()

    output_parts = window.write_group_outputs(cur_headers, cur_rows, config, context, execute_actions=execute_actions)

    final_headers, final_rows, main_stat = build_group_final_output(headers, rows, cur_headers, cur_rows, config)
    stat = build_group_status_text(group_name, source_name, input_stat, main_stat, logs=logs, output_parts=output_parts)
    return final_headers, final_rows, stat
