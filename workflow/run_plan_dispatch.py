# -*- coding: utf-8 -*-
"""Dispatch helpers for PlanWorkflowWindow.run_plan."""


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
    jump_to = None

    if node_type == "循环执行起点":
        headers, rows, stat, ctrl = window.apply_loop_start_node(headers, rows, config, context=context)
        if ctrl.get("no_pending"):
            judge_idx = window.find_loop_judge_index(config.get("loop_id", ""), idx, end, nodes=node_list)
            if judge_idx is not None:
                jump_to = judge_idx + 1
                stat += f"；无待执行项，跳过循环体到节点 {jump_to + 1 if jump_to <= end else '结束'}"
    elif node_type == "循环判断回跳":
        headers, rows, stat, ctrl = window.apply_loop_judge_node(headers, rows, config, context=context)
        if ctrl.get("jump_to") is not None:
            if ctrl.get("jump_to") == "__LOOP_START__":
                jump_to = window.find_loop_start_index(config.get("loop_id", ""), idx, nodes=node_list)
                if jump_to is None:
                    raise RuntimeError(f"未找到循环起点：{config.get('loop_id', '')}")
            else:
                jump_to = int(ctrl["jump_to"])
    elif node_type == "跳转锚点节点":
        headers, rows, stat = window.apply_jump_anchor_node(headers, rows, config, context=context)
    elif node_type == "无条件跳转节点":
        headers, rows, stat, ctrl = window.apply_unconditional_jump_node(
            headers,
            rows,
            config,
            context=context,
            anchors_info=anchors_info,
            nodes=node_list,
        )
        if ctrl.get("jump_to") is not None:
            jump_to = int(ctrl["jump_to"])
    elif node_type == "条件判断节点":
        headers, rows, stat = window.apply_condition_check_node(headers, rows, config, context=context)
    elif node_type == "条件跳转节点":
        headers, rows, stat, ctrl = window.apply_conditional_jump_node(
            headers,
            rows,
            config,
            context=context,
            anchors_info=anchors_info,
            nodes=node_list,
        )
        if ctrl.get("jump_to") is not None:
            jump_to = int(ctrl["jump_to"])
    else:
        headers, rows, stat = window.apply_node(headers, rows, node, execute_actions=execute_actions, context=context)

    return headers, rows, stat, jump_to
