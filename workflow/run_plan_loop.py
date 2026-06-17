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


def execute_run_plan_loop(
    window,
    initial_state,
    execute_actions=False,
    progress_callback=None,
    cancel_event=None,
    suppress_jump_at_stop=False,
    raise_error=False,
    step_executor=None,
):
    node_list = initial_state["node_list"]
    headers = initial_state["headers"]
    rows = initial_state["rows"]
    logs = initial_state["logs"]
    context = initial_state["context"]
    end = initial_state["end"]
    pc = initial_state["pc"]
    steps = initial_state["steps"]
    max_steps = initial_state["max_steps"]
    anchors_info = initial_state["anchors_info"]

    if step_executor is None:
        from workflow.run_plan_step import execute_run_plan_node

        step_executor = execute_run_plan_node

    while should_continue_run_plan(pc, len(node_list), end):
        if stop_if_cancelled(cancel_event, logs):
            break
        steps = advance_run_plan_step(steps, max_steps)

        idx, node = prepare_run_plan_node(window, node_list, pc)
        disabled_next_pc = disabled_node_next_pc(node, idx, logs)
        if disabled_next_pc is not None:
            pc = disabled_next_pc
            continue

        headers, rows, pc, should_stop = step_executor(
            window,
            headers,
            rows,
            logs,
            context,
            node,
            idx,
            end,
            len(node_list),
            steps,
            execute_actions=execute_actions,
            anchors_info=anchors_info,
            node_list=node_list,
            progress_callback=progress_callback,
            suppress_jump_at_stop=suppress_jump_at_stop,
            raise_error=raise_error,
        )
        if should_stop:
            break

    return {
        "headers": headers,
        "rows": rows,
        "logs": logs,
        "context": context,
        "steps": steps,
        "pc": pc,
    }


def build_run_plan_result(headers, rows, logs, context, return_context=False):
    if return_context:
        return headers, rows, logs, context
    return headers, rows, logs
