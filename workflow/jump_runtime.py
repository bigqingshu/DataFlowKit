# -*- coding: utf-8 -*-
"""Runtime helpers for workflow jump nodes."""

from datetime import datetime
import copy


def append_jump_runtime_log(context, event, now_factory=None):
    if not isinstance(context, dict):
        return None
    payload = dict(event or {})
    now = now_factory() if callable(now_factory) else datetime.now()
    payload.setdefault("time", now.strftime("%Y-%m-%d %H:%M:%S"))
    current = context.get("current_node_info", {}) if isinstance(context.get("current_node_info"), dict) else {}
    payload.setdefault("node_id", current.get("node_id", ""))
    payload.setdefault("node_name", current.get("node_name", ""))
    payload.setdefault("node_type", current.get("node_type", ""))
    payload.setdefault("node_index", current.get("node_index", ""))
    context.setdefault("jump_logs", []).append(payload)
    return payload


def apply_jump_anchor_node(window, headers, rows, config, context=None):
    anchor_id = str(config.get("anchor_id", "") or "").strip()
    anchor_name = str(config.get("anchor_name", "") or "").strip()
    detail = f"定位锚点：{anchor_id or '未命名'}"
    if anchor_name:
        detail += f" / {anchor_name}"
    window.append_jump_runtime_log(context, {
        "event": "anchor",
        "anchor_id": anchor_id,
        "anchor_name": anchor_name,
        "status": "ok",
        "message": detail,
    })
    return list(headers), [list(r) for r in rows], detail


def resolve_jump_target_control(window, anchor_id, context=None, anchors_info=None, nodes=None, source="跳转"):
    target_idx, message = window.resolve_jump_anchor_index(anchor_id, anchors_info=anchors_info, nodes=nodes)
    if target_idx is None:
        window.append_jump_runtime_log(context, {
            "event": source,
            "target_anchor_id": str(anchor_id or "").strip(),
            "status": "warning",
            "message": message + "，默认不跳转",
        })
        return {"jump_to": None, "message": message + "，默认不跳转", "status": "warning"}
    window.append_jump_runtime_log(context, {
        "event": source,
        "target_anchor_id": str(anchor_id or "").strip(),
        "target_index": target_idx,
        "status": "ok",
        "message": f"跳转到锚点 {anchor_id}（节点 {target_idx + 1}）",
    })
    return {"jump_to": target_idx, "message": f"跳转到锚点 {anchor_id}（节点 {target_idx + 1}）", "status": "ok"}


def apply_unconditional_jump_node(window, headers, rows, config, context=None, anchors_info=None, nodes=None):
    target = str(config.get("target_anchor_id", "") or "").strip()
    ctrl = window.resolve_jump_target_control(target, context=context, anchors_info=anchors_info, nodes=nodes, source="unconditional_jump")
    return list(headers), [list(r) for r in rows], "无条件跳转：" + ctrl.get("message", ""), ctrl


def condition_count_empty_cells(window, headers, rows, field):
    if field not in headers:
        raise ValueError(f"字段不存在：{field}")
    idx = headers.index(field)
    return sum(1 for row in window.normalize_rows(rows, len(headers)) if window.safe_cell(row, idx).strip() == "")


def condition_count_contains_cells(window, headers, rows, field, value, case_sensitive=True):
    if field not in headers:
        raise ValueError(f"字段不存在：{field}")
    idx = headers.index(field)
    needle = str(value or "")
    if not case_sensitive:
        needle = needle.lower()
    count = 0
    for row in window.normalize_rows(rows, len(headers)):
        text = window.safe_cell(row, idx)
        haystack = text if case_sensitive else text.lower()
        if needle in haystack:
            count += 1
    return count


def evaluate_condition_check_node(window, headers, rows, config, context=None):
    condition_type = str(config.get("condition_type", "表行数") or "表行数").strip()
    field = str(config.get("field", "") or "").strip()
    op = str(config.get("op", "大于") or "大于").strip()
    value = str(config.get("value", "") or "")
    case_sensitive = bool(config.get("case_sensitive", True))
    fixed_rows = window.normalize_rows(rows, len(headers))

    if condition_type == "表行数":
        actual = len(fixed_rows)
        passed = window.compare_values(str(actual), op, value, case_sensitive=True)
        return passed, actual, f"表行数 {actual} {op} {value}"

    if condition_type == "字段是否存在":
        exists = field in headers
        if op in ("不等于", "不包含"):
            passed = not exists
        else:
            passed = exists
        return passed, "TRUE" if exists else "FALSE", f"字段 {field or '-'} {'存在' if exists else '不存在'}"

    if condition_type == "字段值":
        if field not in headers:
            raise ValueError(f"字段不存在：{field}")
        idx = headers.index(field)
        matched = 0
        for row in fixed_rows:
            if window.compare_values(window.safe_cell(row, idx), op, value, case_sensitive=case_sensitive):
                matched += 1
        passed = matched > 0
        return passed, matched, f"字段值任意行满足：{field} {op} {value}，命中 {matched} 行"

    if condition_type == "字段空值数量":
        actual = window.condition_count_empty_cells(headers, fixed_rows, field)
        passed = window.compare_values(str(actual), op, value, case_sensitive=True)
        return passed, actual, f"字段空值数量：{field}={actual}，条件 {op} {value}"

    if condition_type == "字段包含值数量":
        actual = window.condition_count_contains_cells(headers, fixed_rows, field, value, case_sensitive=case_sensitive)
        passed = window.compare_values(str(actual), op, value, case_sensitive=True)
        return passed, actual, f"字段包含值数量：{field} 包含 {value} 的行数={actual}，条件 {op} {value}"

    raise ValueError(f"未知条件判断类型：{condition_type}")


def apply_condition_check_node(window, headers, rows, config, context=None, now_factory=None):
    context = context if isinstance(context, dict) else {}
    flag_name = str(config.get("flag_name", "") or "").strip()
    if not flag_name:
        raise ValueError("条件判断节点未填写输出标志。")
    passed, actual_value, detail = window.evaluate_condition_check_node(headers, rows, config, context=context)
    output_value = str(config.get("true_value", "TRUE") if passed else config.get("false_value", "FALSE"))
    now = now_factory() if callable(now_factory) else datetime.now()
    item = {
        "value": output_value,
        "passed": bool(passed),
        "actual": actual_value,
        "detail": detail,
        "source_node": copy.deepcopy(context.get("current_node_info", {})) if isinstance(context, dict) else {},
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
    }
    context.setdefault("condition_flags", {})[flag_name] = item
    window.append_jump_runtime_log(context, {
        "event": "condition_check",
        "flag_name": flag_name,
        "value": output_value,
        "passed": bool(passed),
        "actual": actual_value,
        "status": "ok",
        "message": detail,
    })
    return list(headers), [list(r) for r in rows], f"条件判断：{flag_name}={output_value}；{detail}"


def find_conditional_jump_target(flag_value, config):
    value_text = str(flag_value or "").strip()
    rules = config.get("jump_rules", [])
    if not isinstance(rules, list):
        rules = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        expected = str(rule.get("value", "") or "").strip()
        if expected == value_text:
            return str(rule.get("target_anchor_id", "") or "").strip(), f"命中条件值 {value_text}"
    default_anchor = str(config.get("default_anchor_id", "") or "").strip()
    if default_anchor:
        return default_anchor, f"条件值 {value_text or '-'} 未映射，使用默认锚点"
    return "", f"条件值 {value_text or '-'} 未映射"


def apply_conditional_jump_node(window, headers, rows, config, context=None, anchors_info=None, nodes=None):
    context = context if isinstance(context, dict) else {}
    flag_name = str(config.get("flag_name", "") or "").strip()
    if not flag_name:
        message = "条件跳转未填写读取标志，默认不跳转"
        window.append_jump_runtime_log(context, {
            "event": "conditional_jump",
            "flag_name": flag_name,
            "status": "warning",
            "message": message,
        })
        return list(headers), [list(r) for r in rows], message, {"jump_to": None, "message": message, "status": "warning"}
    flags = context.setdefault("condition_flags", {})
    if flag_name not in flags:
        message = f"条件标志未产生：{flag_name}，默认不跳转"
        window.append_jump_runtime_log(context, {
            "event": "conditional_jump",
            "flag_name": flag_name,
            "status": "warning",
            "message": message,
        })
        return list(headers), [list(r) for r in rows], message, {"jump_to": None, "message": message, "status": "warning"}

    flag_item = flags.get(flag_name, {}) or {}
    flag_value = str(flag_item.get("value", "") or "").strip()
    target, rule_message = window.find_conditional_jump_target(flag_value, config)
    if not target:
        message = f"条件跳转：{flag_name}={flag_value or '-'}；{rule_message}，默认不跳转"
        window.append_jump_runtime_log(context, {
            "event": "conditional_jump",
            "flag_name": flag_name,
            "flag_value": flag_value,
            "status": "warning",
            "message": message,
        })
        return list(headers), [list(r) for r in rows], message, {"jump_to": None, "message": message, "status": "warning"}

    ctrl = window.resolve_jump_target_control(target, context=context, anchors_info=anchors_info, nodes=nodes, source="conditional_jump")
    stat = f"条件跳转：{flag_name}={flag_value or '-'}；{rule_message}；{ctrl.get('message', '')}"
    return list(headers), [list(r) for r in rows], stat, ctrl
