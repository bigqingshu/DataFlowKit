# -*- coding: utf-8 -*-
"""Context and input initialization helpers for run_plan."""


def build_run_plan_initial_state(
    window,
    stop_index=None,
    start_index=0,
    initial_headers=None,
    initial_rows=None,
    initial_context=None,
    progress_callback=None,
    cancel_event=None,
    workflow_snapshot=None,
    normalize_policy=None,
):
    snapshot = workflow_snapshot or {}
    node_list = snapshot.get("nodes") if isinstance(snapshot, dict) and snapshot.get("nodes") is not None else window.nodes

    if initial_headers is not None:
        headers = list(initial_headers)
    elif isinstance(snapshot, dict) and snapshot.get("headers") is not None:
        headers = list(snapshot.get("headers") or [])
    else:
        headers = list(window.app.headers)

    if initial_rows is not None:
        rows = [list(row) for row in initial_rows]
    elif isinstance(snapshot, dict) and snapshot.get("rows") is not None:
        rows = [list(row) for row in (snapshot.get("rows") or [])]
    else:
        rows = [list(row) for row in window.app.rows]

    context = initial_context if initial_context is not None else {"transit_tables": {}, "loop_states": {}, "loop_results": {}}
    context.setdefault("transit_tables", {})
    context.setdefault("loop_states", {})
    context.setdefault("loop_results", {})
    context.setdefault("condition_flags", {})
    context.setdefault("jump_logs", [])

    if isinstance(snapshot, dict) and snapshot.get("table_access_policy") is not None:
        if not callable(normalize_policy):
            raise ValueError("normalize_policy is required when workflow_snapshot contains table_access_policy")
        context["table_access_policy"] = normalize_policy(snapshot.get("table_access_policy"))
    else:
        context.setdefault("table_access_policy", window.normalize_table_access_policy())

    if snapshot:
        context["workflow_snapshot"] = snapshot
    if progress_callback is not None:
        context["progress_callback"] = progress_callback
    if cancel_event is not None:
        context["cancel_event"] = cancel_event

    end = len(node_list) - 1 if stop_index is None else stop_index
    return {
        "snapshot": snapshot,
        "node_list": node_list,
        "headers": headers,
        "rows": rows,
        "logs": [],
        "context": context,
        "end": end,
        "pc": int(start_index or 0),
        "steps": 0,
        "max_steps": max(1000, len(node_list) * 2000),
        "anchors_info": window.collect_jump_anchors(nodes=node_list),
    }
