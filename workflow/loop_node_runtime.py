# -*- coding: utf-8 -*-
"""Window adapters for loop workflow node execution."""

from workflow.nodes.loop_nodes import (
    apply_loop_judge_to_state,
    build_loop_judge_output,
    build_loop_start_output,
    init_loop_state_from_source,
    take_next_loop_item,
)


def get_loop_source_table_data(window, headers, rows, config, context=None):
    source_type = config.get("source_type", "当前表")
    if source_type == "当前表":
        return list(headers), [list(r) for r in rows], "当前表"
    if source_type == "SQLite表":
        table_name = config.get("source_table", "")
        if not table_name:
            raise ValueError("循环执行起点未选择 SQLite 来源表。")
        db = window.get_table_manager(context if isinstance(context, dict) else None, node_type="循环执行起点")
        data = db.read_table(table_name)
        return list(data.get("headers", [])), [list(r) for r in data.get("rows", [])], f"SQLite:{table_name}"
    if source_type == "中转副表":
        name = config.get("transit_table", "")
        manager = window.check_transit_table_permission(
            context,
            name,
            ["read_table"],
            operation="read_transit_table",
            field_action="read",
            node_type="循环执行起点",
        )
        tables = (context or {}).get("transit_tables", {})
        if name not in tables:
            raise ValueError(f"未找到中转副表：{name}")
        data = tables[name]
        source_headers = list(data.get("headers", []))
        source_rows = [list(r) for r in data.get("rows", [])]
        window.log_transit_table_event(
            manager,
            "read_transit_table",
            name,
            source_headers,
            source_rows,
            message=f"循环执行起点读取中转副表 {name}：{len(source_rows)} 行 × {len(source_headers)} 列",
        )
        return source_headers, source_rows, f"中转:{name}"
    return list(headers), [list(r) for r in rows], "当前表"


def init_loop_state_for_window(window, headers, rows, config, context=None):
    source_headers, source_rows, source_name = get_loop_source_table_data(
        window,
        headers,
        rows,
        config,
        context=context,
    )
    return init_loop_state_from_source(source_headers, source_rows, source_name, config)


def apply_loop_start_node_for_window(window, headers, rows, config, context=None):
    context = context if context is not None else {}
    states = context.setdefault("loop_states", {})
    loop_id = config.get("loop_id", "loop") or "loop"
    state = states.get(loop_id)
    if state is None:
        state = init_loop_state_for_window(window, headers, rows, config, context=context)
        states[loop_id] = state
    start_result = take_next_loop_item(state)
    table_name = start_result["table_name"]
    current_headers = start_result["current_headers"]
    transit_rows = start_result["transit_rows"]
    transit_tables = context.setdefault("transit_tables", {})
    manager = window.check_transit_table_write_permission(
        context,
        table_name,
        exists=table_name in transit_tables,
        write_mode="覆盖当前循环项",
        fields=current_headers,
        node_type="循环执行起点",
    )
    transit_tables[table_name] = {
        "headers": list(current_headers),
        "rows": [list(r) for r in transit_rows],
        "source": start_result["transit_source"],
    }
    if start_result.get("no_pending"):
        message = f"循环执行起点写入空当前项中转副表 {table_name}"
    else:
        message = f"循环执行起点写入当前项中转副表 {table_name}：1 行 × {len(current_headers)} 列"
    window.log_transit_table_event(
        manager,
        "write_transit_table",
        table_name,
        current_headers,
        transit_rows,
        write_mode="覆盖当前循环项",
        message=message,
    )
    return build_loop_start_output(
        headers,
        rows,
        start_result,
        output_current_as_table=config.get("output_current_as_table", True),
    )


def apply_loop_judge_node_for_window(window, headers, rows, config, context=None):
    context = context if context is not None else {}
    loop_id = config.get("loop_id", "")
    if not loop_id:
        raise ValueError("循环判断回跳节点未绑定循环执行起点。")
    state = context.setdefault("loop_states", {}).get(loop_id)
    if not state:
        raise ValueError(f"未找到循环状态：{loop_id}。请确认循环执行起点在本节点之前。")
    judge_result = apply_loop_judge_to_state(headers, rows, config, state)
    if judge_result.get("no_current"):
        return headers, rows, judge_result["stat"], judge_result["ctrl"]
    result_headers = judge_result["result_headers"]
    result_row = judge_result["result_row"]
    results = context.setdefault("loop_results", {}).setdefault(loop_id, {"headers": result_headers, "rows": []})
    results["rows"].append(result_row)
    result_name = config.get("result_table_name", "循环结果") or "循环结果"
    transit_tables = context.setdefault("transit_tables", {})
    result_rows = [list(r) for r in results["rows"]]
    result_manager = window.check_transit_table_write_permission(
        context,
        result_name,
        exists=result_name in transit_tables,
        write_mode="覆盖循环结果",
        fields=result_headers,
        node_type="循环判断回跳",
    )
    transit_tables[result_name] = {"headers": result_headers, "rows": result_rows, "source": f"循环:{loop_id}:结果"}
    window.log_transit_table_event(
        result_manager,
        "write_transit_table",
        result_name,
        result_headers,
        result_rows,
        write_mode="覆盖循环结果",
        message=f"循环判断回跳写入结果中转副表 {result_name}：{len(result_rows)} 行 × {len(result_headers)} 列",
    )
    queue_name = judge_result["queue_name"]
    queue_rows = judge_result["queue_rows"]
    queue_headers = judge_result["queue_headers"]
    queue_manager = window.check_transit_table_write_permission(
        context,
        queue_name,
        exists=queue_name in transit_tables,
        write_mode="覆盖循环队列",
        fields=queue_headers,
        node_type="循环判断回跳",
    )
    transit_tables[queue_name] = {"headers": list(queue_headers), "rows": queue_rows, "source": f"循环:{loop_id}:队列"}
    window.log_transit_table_event(
        queue_manager,
        "write_transit_table",
        queue_name,
        queue_headers,
        queue_rows,
        write_mode="覆盖循环队列",
        message=f"循环判断回跳写入队列中转副表 {queue_name}：{len(queue_rows)} 行 × {len(queue_headers)} 列",
    )
    return build_loop_judge_output(headers, rows, config, state, judge_result, results["rows"])
