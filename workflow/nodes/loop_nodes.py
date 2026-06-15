# -*- coding: utf-8 -*-
"""Pure helpers for loop workflow nodes."""

import re
from datetime import datetime

from core.data_utils import normalize_rows, safe_cell


LOOP_RESULT_HEADERS = ["循环名称", "循环序号", "队列行号", "判断结果", "标记状态", "说明", "时间"]


def loop_last_non_empty_row_index(headers, rows, field):
    if field not in headers:
        return len(rows) - 1
    idx = headers.index(field)
    for i in range(len(rows) - 1, -1, -1):
        if safe_cell(rows[i], idx).strip() != "":
            return i
    return -1


def get_loop_source_rows_for_boundary(source_headers, source_rows, config):
    normalized = normalize_rows(source_rows, len(source_headers))
    boundary_mode = config.get("boundary_mode", "整体表格数据边界")
    if boundary_mode == "指定参考列数据边界":
        last_idx = loop_last_non_empty_row_index(source_headers, normalized, config.get("reference_field", ""))
        return normalized[:last_idx + 1] if last_idx >= 0 else []
    if boundary_mode == "手动指定行数":
        try:
            count = max(0, int(str(config.get("manual_count", "0")).strip()))
        except Exception:
            count = len(normalized)
        return normalized[:count]
    return normalized


def init_loop_state_from_source(source_headers, source_rows, source_name, config):
    loop_id = config.get("loop_id", "loop") or "loop"
    source_headers = list(source_headers or [])
    source_rows_use = get_loop_source_rows_for_boundary(source_headers, source_rows, config)
    selected_fields = [field for field in (config.get("fields") or source_headers) if field in source_headers]
    if not selected_fields:
        selected_fields = list(source_headers)
    flag_field = config.get("flag_field", "执行标志") or "执行标志"
    flag_idx = source_headers.index(flag_field) if flag_field in source_headers else None
    init_mode = config.get("init_flag_mode", "空值填0，非0不执行")
    running_policy = config.get("running_flag_policy", "执行中1标记失败3")
    queue_headers = [flag_field, "原始行号"] + selected_fields
    queue_rows = []
    for i, row in enumerate(source_rows_use):
        if init_mode == "强制重置全部为0" or flag_idx is None:
            flag = "0"
        else:
            flag = safe_cell(row, flag_idx).strip()
            if flag == "" and init_mode == "空值填0，非0不执行":
                flag = "0"
            if flag == "1":
                if running_policy == "执行中1标记失败3":
                    flag = "3"
                elif running_policy == "执行中1重置为0":
                    flag = "0"
        queue_rows.append([flag, str(i + 1)] + [safe_cell(row, source_headers.index(field)) for field in selected_fields])
    return {
        "loop_id": loop_id,
        "queue_headers": queue_headers,
        "queue_rows": queue_rows,
        "selected_fields": selected_fields,
        "current_index": None,
        "iterations": 0,
        "source_name": source_name,
        "current_table_name": config.get("current_table_name", "当前循环项") or "当前循环项",
        "max_loop_count": int(str(config.get("max_loop_count", "10000") or "10000")),
    }


def find_next_pending_loop_index(state):
    for i, row in enumerate(state.get("queue_rows", []) or []):
        if str(row[0]).strip() == "0":
            return i
    return None


def take_next_loop_item(state):
    loop_id = state.get("loop_id", "loop") or "loop"
    if state.get("iterations", 0) > state.get("max_loop_count", 10000):
        raise ValueError(f"循环 {loop_id} 超过最大循环次数，疑似死循环。")

    current_headers = list(state.get("queue_headers", [])[2:])
    pending_idx = find_next_pending_loop_index(state)
    if pending_idx is None:
        return {
            "no_pending": True,
            "table_name": state.get("current_table_name", "当前循环项") or "当前循环项",
            "current_headers": current_headers,
            "current_row": [],
            "transit_rows": [],
            "transit_source": f"循环:{loop_id}:无待执行",
            "output_headers": None,
            "output_rows": None,
            "stat": f"循环 {loop_id} 无待执行项",
            "ctrl": {"no_pending": True},
        }

    state["queue_rows"][pending_idx][0] = "1"
    state["current_index"] = pending_idx
    state["iterations"] = state.get("iterations", 0) + 1
    current_row = list(state["queue_rows"][pending_idx][2:])
    output_current = True
    stat = f"循环 {loop_id} 取第 {pending_idx + 1} 条，标志 0→1"
    return {
        "no_pending": False,
        "table_name": state.get("current_table_name", "当前循环项") or "当前循环项",
        "current_headers": current_headers,
        "current_row": current_row,
        "transit_rows": [current_row],
        "transit_source": f"循环:{loop_id}:当前项",
        "output_headers": current_headers if output_current else None,
        "output_rows": [current_row] if output_current else None,
        "stat": stat,
        "ctrl": {"no_pending": False},
        "pending_index": pending_idx,
    }


def build_loop_start_output(headers, rows, start_result, output_current_as_table=True):
    if start_result.get("no_pending"):
        return list(headers), [list(r) for r in rows], start_result["stat"], start_result["ctrl"]
    if output_current_as_table:
        return (
            list(start_result.get("current_headers", [])),
            [list(start_result.get("current_row", []))],
            start_result["stat"],
            start_result["ctrl"],
        )
    return (
        list(headers),
        [list(r) for r in rows],
        start_result["stat"] + "，当前表保持不变",
        start_result["ctrl"],
    )


def evaluate_loop_condition(headers, rows, config, loop_state=None):
    mode = config.get("condition_mode", "始终成功")
    if mode == "始终成功":
        return True, "始终成功"
    if mode == "结果表行数>0":
        return len(rows) > 0, f"当前结果行数={len(rows)}"
    check_headers, check_rows = headers, rows
    if config.get("condition_source") == "当前循环项表" and loop_state is not None:
        check_headers = loop_state.get("queue_headers", [])[2:]
        current_index = loop_state.get("current_index")
        check_rows = [loop_state.get("queue_rows", [])[current_index][2:]] if current_index is not None else []
    field = config.get("condition_field", "")
    if field not in check_headers:
        return False, f"判断字段不存在：{field}"
    idx = check_headers.index(field)
    value = config.get("condition_value", "")
    if not check_rows:
        return False, "判断数据为空"
    text = safe_cell(check_rows[0], idx)
    if mode == "字段等于":
        return text == value, f"{field}={text}"
    if mode == "字段不等于":
        return text != value, f"{field}={text}"
    if mode == "字段包含":
        return str(value) in text, f"{field}={text}"
    if mode == "字段不为空":
        return text.strip() != "", f"{field}={text}"
    if mode == "正则匹配":
        try:
            return re.search(str(value), text) is not None, f"{field}={text}"
        except Exception as exc:
            return False, f"正则错误：{exc}"
    return True, "默认成功"


def apply_loop_judge_to_state(headers, rows, config, state, now_text=None):
    loop_id = config.get("loop_id", "")
    current_index = state.get("current_index")
    if current_index is None:
        return {
            "headers": list(headers),
            "rows": [list(r) for r in rows],
            "stat": f"循环 {loop_id} 当前无执行项",
            "ctrl": {"jump_to": None},
            "no_current": True,
        }

    ok, detail = evaluate_loop_condition(headers, rows, config, loop_state=state)
    if ok:
        state["queue_rows"][current_index][0] = "2"
        status_text = "完成2"
    else:
        fail_policy = config.get("on_fail", "标记失败3并继续下一条")
        if fail_policy == "重置为0稍后重试":
            state["queue_rows"][current_index][0] = "0"
            status_text = "重置0"
        elif fail_policy == "标记跳过4并继续下一条":
            state["queue_rows"][current_index][0] = "4"
            status_text = "跳过4"
        else:
            state["queue_rows"][current_index][0] = "3"
            status_text = "失败3"
            if fail_policy == "标记失败3并停止工作流":
                raise ValueError(f"循环 {loop_id} 条件不满足，已标记失败：{detail}")

    result_row = [
        loop_id,
        str(state.get("iterations", 0)),
        str(current_index + 1),
        "满足" if ok else "不满足",
        status_text,
        detail,
        now_text or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ]
    state["current_index"] = None
    has_pending = any(str(row[0]).strip() == "0" for row in state.get("queue_rows", []) or [])
    return {
        "ok": ok,
        "detail": detail,
        "status_text": status_text,
        "result_headers": list(LOOP_RESULT_HEADERS),
        "result_row": result_row,
        "queue_name": f"循环队列_{loop_id}",
        "queue_headers": list(state.get("queue_headers", [])),
        "queue_rows": [list(r) for r in state.get("queue_rows", [])],
        "has_pending": has_pending,
    }


def build_loop_judge_output(headers, rows, config, state, judge_result, result_rows):
    loop_id = config.get("loop_id", "")
    if judge_result.get("has_pending"):
        return (
            list(headers),
            [list(r) for r in rows],
            f"循环 {loop_id} {judge_result.get('status_text')}，仍有待执行项，准备回跳",
            {"jump_to": "__LOOP_START__"},
        )

    mode = config.get("end_output_mode", "循环队列表")
    if mode == "循环队列表":
        return (
            list(state.get("queue_headers", [])),
            [list(r) for r in state.get("queue_rows", [])],
            f"循环 {loop_id} 已全部结束，输出循环队列表",
            {"jump_to": None},
        )
    if mode == "循环结果表":
        return (
            list(LOOP_RESULT_HEADERS),
            [list(r) for r in result_rows],
            f"循环 {loop_id} 已全部结束，输出循环结果表",
            {"jump_to": None},
        )
    return list(headers), [list(r) for r in rows], f"循环 {loop_id} 已全部结束，保持当前表", {"jump_to": None}


def find_loop_start_index(loop_id, current_idx, nodes):
    for i in range(current_idx - 1, -1, -1):
        node = nodes[i]
        if node.get("enabled", True) and node.get("type") == "循环执行起点" and node.get("config", {}).get("loop_id") == loop_id:
            return i
    return None


def find_loop_judge_index(loop_id, start_idx, end_idx, nodes):
    for i in range(start_idx + 1, min(len(nodes), end_idx + 1)):
        node = nodes[i]
        if node.get("enabled", True) and node.get("type") == "循环判断回跳" and node.get("config", {}).get("loop_id") == loop_id:
            return i
    return None
