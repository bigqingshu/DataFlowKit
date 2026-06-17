# -*- coding: utf-8 -*-
"""Per-node helpers for PlanWorkflowWindow.run_plan."""

import copy


JUMP_NODE_TYPES = ("跳转锚点节点", "无条件跳转节点", "条件跳转节点")


def set_current_node_info(context, node, node_type, idx):
    info = {
        "node_id": node.get("node_id", ""),
        "node_name": node.get("name", ""),
        "node_type": node_type,
        "node_index": idx,
        "table_access": copy.deepcopy(node.get("table_access", {})),
    }
    context["current_node_info"] = info
    return info


def emit_node_start(progress_callback, idx, node_total, steps, node_type):
    if progress_callback is None:
        return None
    payload = {
        "type": "node_start",
        "node_index": idx,
        "node_total": node_total,
        "step": steps,
        "node_name": node_type,
        "message": f"开始执行节点 {idx + 1}.{node_type}",
    }
    progress_callback(payload)
    return payload


def emit_node_done(progress_callback, idx, node_total, steps, node_type, headers, rows):
    if progress_callback is None:
        return None
    payload = {
        "type": "node_done",
        "node_index": idx,
        "node_total": node_total,
        "step": steps,
        "node_name": node_type,
        "rows": len(rows),
        "cols": len(headers),
        "message": f"完成节点 {idx + 1}.{node_type}：{len(rows)} 行 × {len(headers)} 列",
    }
    progress_callback(payload)
    return payload


def emit_node_error(progress_callback, idx, node_total, node_type, error):
    if progress_callback is None:
        return None
    payload = {
        "type": "node_error",
        "node_index": idx,
        "node_total": node_total,
        "node_name": node_type,
        "message": f"节点 {idx + 1}.{node_type} 执行失败：{error}",
    }
    progress_callback(payload)
    return payload


def get_current_table_manager(window, context, headers, node_type):
    if node_type in JUMP_NODE_TYPES:
        return window.get_table_manager(context, node_type=node_type)
    manager = window.check_current_table_permission(
        context,
        headers,
        write=False,
        operation="read_current_table",
    )
    if node_type != "条件判断节点":
        manager = window.check_current_table_permission(
            context,
            headers,
            write=True,
            operation="write_current_table",
        )
    return manager


def build_node_run_log(idx, node_type, before_shape, headers, rows, stat):
    after_shape = (len(rows), len(headers))
    return f"{idx+1}.{node_type} {before_shape[0]}×{before_shape[1]}→{after_shape[0]}×{after_shape[1]} {stat}"


def prepare_node_execution(context, node, idx, node_total, steps, progress_callback):
    node_type = node.get("type")
    config = node.get("config", {})
    set_current_node_info(context, node, node_type, idx)
    emit_node_start(progress_callback, idx, node_total, steps, node_type)
    return node_type, config


def begin_node_execution(window, context, headers, rows, node_type):
    before_shape = (len(rows), len(headers))
    current_table_manager = get_current_table_manager(window, context, headers, node_type)
    return before_shape, current_table_manager


def resolve_next_pc(idx, jump_to, node_total):
    if jump_to is not None:
        if jump_to < 0 or jump_to > node_total:
            raise RuntimeError(f"循环跳转目标越界：{jump_to}")
        return jump_to
    return idx + 1


def finish_node_execution(
    window,
    logs,
    current_table_manager,
    before_shape,
    idx,
    node_type,
    config,
    headers,
    rows,
    stat,
    jump_to,
    end,
    node_total,
    steps,
    progress_callback,
    suppress_jump_at_stop=False,
):
    window.log_current_table_transform(
        current_table_manager,
        before_shape,
        headers,
        rows,
        node_type=node_type,
    )
    logs.append(build_node_run_log(idx, node_type, before_shape, headers, rows, stat))
    emit_node_done(progress_callback, idx, node_total, steps, node_type, headers, rows)

    if node_type == "保存中转数据" and config.get("stop_after_save"):
        logs.append(f"节点 {idx+1}.保存中转数据 已设置保存后停止，流程在此停止。")
        return None, True

    if jump_to is not None and suppress_jump_at_stop and idx >= end:
        jump_to = None

    return resolve_next_pc(idx, jump_to, node_total), False


def handle_node_execution_error(progress_callback, logs, idx, node_total, node_type, error, raise_error=False):
    emit_node_error(progress_callback, idx, node_total, node_type, error)
    if raise_error:
        raise RuntimeError(f"第 {idx+1} 个节点【{node_type}】执行失败：{error}")
    logs.append(f"失败 {idx+1}.{node_type}：{error}")
    return idx + 1
