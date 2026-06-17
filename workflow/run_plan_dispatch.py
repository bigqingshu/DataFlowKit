# -*- coding: utf-8 -*-
"""Dispatch helpers for PlanWorkflowWindow.run_plan."""

from workflow.jump_runtime import (
    apply_condition_check_node,
    apply_conditional_jump_node,
    apply_jump_anchor_node,
    apply_unconditional_jump_node,
)
from workflow.loop_node_runtime import (
    apply_loop_judge_node_for_window,
    apply_loop_start_node_for_window,
)


def dispatch_loop_start_node(window, headers, rows, config, context, idx=0, end=None, node_list=None):
    headers, rows, stat, ctrl = apply_loop_start_node_for_window(window, headers, rows, config, context=context)
    jump_to = None
    if ctrl.get("no_pending"):
        judge_idx = window.find_loop_judge_index(config.get("loop_id", ""), idx, end, nodes=node_list)
        if judge_idx is not None:
            jump_to = judge_idx + 1
            stat += f"；无待执行项，跳过循环体到节点 {jump_to + 1 if jump_to <= end else '结束'}"
    return headers, rows, stat, jump_to


def dispatch_loop_judge_node(window, headers, rows, config, context, idx=0, node_list=None):
    headers, rows, stat, ctrl = apply_loop_judge_node_for_window(window, headers, rows, config, context=context)
    jump_to = None
    if ctrl.get("jump_to") is not None:
        if ctrl.get("jump_to") == "__LOOP_START__":
            jump_to = window.find_loop_start_index(config.get("loop_id", ""), idx, nodes=node_list)
            if jump_to is None:
                raise RuntimeError(f"未找到循环起点：{config.get('loop_id', '')}")
        else:
            jump_to = int(ctrl["jump_to"])
    return headers, rows, stat, jump_to


def dispatch_unconditional_jump_node(window, headers, rows, config, context, anchors_info=None, node_list=None):
    headers, rows, stat, ctrl = apply_unconditional_jump_node(
        window,
        headers,
        rows,
        config,
        context=context,
        anchors_info=anchors_info,
        nodes=node_list,
    )
    jump_to = int(ctrl["jump_to"]) if ctrl.get("jump_to") is not None else None
    return headers, rows, stat, jump_to


def dispatch_conditional_jump_node(window, headers, rows, config, context, anchors_info=None, node_list=None):
    headers, rows, stat, ctrl = apply_conditional_jump_node(
        window,
        headers,
        rows,
        config,
        context=context,
        anchors_info=anchors_info,
        nodes=node_list,
    )
    jump_to = int(ctrl["jump_to"]) if ctrl.get("jump_to") is not None else None
    return headers, rows, stat, jump_to


def dispatch_loop_node(window, headers, rows, node_type, config, context, idx=0, end=None, node_list=None):
    if node_type == "循环执行起点":
        return dispatch_loop_start_node(
            window,
            headers,
            rows,
            config,
            context,
            idx=idx,
            end=end,
            node_list=node_list,
        )
    if node_type == "循环判断回跳":
        return dispatch_loop_judge_node(
            window,
            headers,
            rows,
            config,
            context,
            idx=idx,
            node_list=node_list,
        )
    return None


def dispatch_jump_node(window, headers, rows, node_type, config, context, anchors_info=None, node_list=None):
    if node_type == "跳转锚点节点":
        headers, rows, stat = apply_jump_anchor_node(window, headers, rows, config, context=context)
        return headers, rows, stat, None
    if node_type == "无条件跳转节点":
        return dispatch_unconditional_jump_node(
            window,
            headers,
            rows,
            config,
            context,
            anchors_info=anchors_info,
            node_list=node_list,
        )
    if node_type == "条件判断节点":
        headers, rows, stat = apply_condition_check_node(window, headers, rows, config, context=context)
        return headers, rows, stat, None
    if node_type == "条件跳转节点":
        return dispatch_conditional_jump_node(
            window,
            headers,
            rows,
            config,
            context,
            anchors_info=anchors_info,
            node_list=node_list,
        )
    return None


def dispatch_regular_run_plan_node(window, headers, rows, node, context, execute_actions=False):
    headers, rows, stat = window.apply_node(
        headers,
        rows,
        node,
        execute_actions=execute_actions,
        context=context,
    )
    return headers, rows, stat, None


def dispatch_run_plan_node(
    window,
    headers,
    rows,
    node,
    context,
    execute_actions=False,
    anchors_info=None,
    node_list=None,
    idx=0,
    end=None,
):
    node_type = node.get("type")
    config = node.get("config", {})

    loop_result = dispatch_loop_node(
        window,
        headers,
        rows,
        node_type,
        config,
        context,
        idx=idx,
        end=end,
        node_list=node_list,
    )
    if loop_result is not None:
        return loop_result

    jump_result = dispatch_jump_node(
        window,
        headers,
        rows,
        node_type,
        config,
        context,
        anchors_info=anchors_info,
        node_list=node_list,
    )
    if jump_result is not None:
        return jump_result

    return dispatch_regular_run_plan_node(
        window,
        headers,
        rows,
        node,
        context,
        execute_actions=execute_actions,
    )
