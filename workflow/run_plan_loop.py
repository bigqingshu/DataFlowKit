# -*- coding: utf-8 -*-
"""Loop-control helpers for PlanWorkflowWindow.run_plan."""


CANCELLED_RUN_LOG = "用户取消后台执行，工作流已安全停止。"
MAX_STEPS_ERROR = "工作流执行步数超过安全上限，疑似循环未正确结束。"


def should_continue_run_plan(pc, node_total, end):
    return pc < node_total and pc <= end


def is_run_cancelled(cancel_event):
    return cancel_event is not None and cancel_event.is_set()


def append_cancelled_run_log(logs):
    logs.append(CANCELLED_RUN_LOG)
    return True


def stop_if_cancelled(cancel_event, logs):
    if is_run_cancelled(cancel_event):
        return append_cancelled_run_log(logs)
    return False


def advance_run_plan_step(steps, max_steps):
    next_steps = steps + 1
    if next_steps > max_steps:
        raise RuntimeError(MAX_STEPS_ERROR)
    return next_steps


def prepare_run_plan_node(window, node_list, pc):
    idx = pc
    node = node_list[idx]
    window.ensure_node_identity(node)
    window.refresh_node_table_access(node)
    return idx, node


def disabled_node_next_pc(node, idx, logs):
    if node.get("enabled", True):
        return None
    logs.append(f"跳过 {idx+1}.{node.get('type')}")
    return idx + 1
