# -*- coding: utf-8 -*-
"""UI-free node configuration validation helpers."""

from __future__ import annotations

import re

from engine.issue_schema import has_error_issues, make_issue
from workflow.nodes.new_column_nodes import parse_new_columns_specs
from workflow.protocol_nodes import (
    display_type_for_node_type_id,
    normalize_node_type_id,
    stable_node_type_id_for_node,
)


SUPPORTED_CONFIG_VALIDATION_NODE_IDS = {
    "core.new_columns",
    "core.replace",
    "core.merge_columns",
    "core.filter",
}

REPLACE_MATCH_MODES = {
    "等于",
    "完全相等",
    "不等于",
    "包含",
    "不包含",
    "开头是",
    "结尾是",
    "为空",
    "不为空",
    "正则匹配",
    "大于",
    "小于",
    "大于等于",
    "小于等于",
}

REPLACE_MODES = {
    "局部替换匹配字符串",
    "整格替换为新值",
}

FILTER_CONDITION_OPS = {
    "等于",
    "完全相等",
    "不等于",
    "包含",
    "不包含",
    "开头是",
    "结尾是",
    "为空",
    "不为空",
    "正则匹配",
    "大于",
    "小于",
    "大于等于",
    "小于等于",
}

FILTER_JOIN_OPS = {
    "等于",
    "不等于",
    "左包含右",
    "右包含左",
    "双向包含",
}


def validate_node_config(
    node_or_type,
    config=None,
    *,
    headers=None,
    table_names=None,
    table_columns=None,
):
    """Validate a node config and return ``{ok, issues, node_type_id}``."""

    node_type_id, payload = _resolve_node_and_config(node_or_type, config)
    headers = [str(item) for item in (headers or [])]
    table_names = [str(item) for item in (table_names or [])]
    table_columns = table_columns or {}
    issues = []

    if not isinstance(payload, dict):
        issues.append(_issue("error", "invalid_config", "节点配置必须是 object。", path="/config"))
        return _result(node_type_id, issues)

    if not node_type_id:
        issues.append(_issue("error", "missing_node_type", "节点缺少 node_type_id/type。", path="/node_type_id"))
        return _result(node_type_id, issues)

    stable_id = normalize_node_type_id(node_type_id)
    if stable_id == "core.new_columns":
        _validate_new_columns(payload, headers, issues)
    elif stable_id == "core.replace":
        _validate_replace(payload, headers, issues)
    elif stable_id == "core.merge_columns":
        _validate_merge_columns(payload, headers, issues)
    elif stable_id == "core.filter":
        _validate_filter(payload, headers, table_names, table_columns, issues)
    else:
        issues.append(_issue(
            "info",
            "config_validation_not_covered",
            f"暂未为节点【{display_type_for_node_type_id(stable_id)}】提供精细配置校验。",
            path="/config",
        ))
    return _result(stable_id, issues)


def validate_plan_configs(plan, *, headers=None, table_names=None, table_columns=None):
    issues = []
    nodes = []
    if isinstance(plan, dict):
        nodes = plan.get("nodes", [])
        if headers is None:
            headers = plan.get("headers", [])
    elif isinstance(plan, list):
        nodes = plan
    else:
        issues.append(_issue("error", "invalid_plan", "plan 必须是 object 或节点 list。", path="/plan"))
        return {"ok": False, "issues": issues, "node_count": 0}

    if not isinstance(nodes, list):
        issues.append(_issue("error", "invalid_nodes", "plan.nodes 必须是 list。", path="/nodes"))
        return {"ok": False, "issues": issues, "node_count": 0}

    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            issues.append(_issue("error", "invalid_node", "节点必须是 object。", path=f"/nodes/{index}", node_index=index))
            continue
        result = validate_node_config(
            node,
            headers=headers,
            table_names=table_names,
            table_columns=table_columns,
        )
        for issue in result.get("issues", []):
            item = dict(issue)
            item.setdefault("node_index", index)
            item.setdefault("node_type_id", result.get("node_type_id", ""))
            item.setdefault("node_type", display_type_for_node_type_id(result.get("node_type_id", "")))
            if item.get("path", "").startswith("/"):
                item["path"] = f"/nodes/{index}" + item["path"]
            issues.append(item)
    return {
        "ok": not has_error_issues(issues),
        "issues": issues,
        "node_count": len(nodes),
    }


def _resolve_node_and_config(node_or_type, config):
    if isinstance(node_or_type, dict):
        return stable_node_type_id_for_node(node_or_type), node_or_type.get("config", {})
    return normalize_node_type_id(node_or_type), ({} if config is None else config)


def _validate_new_columns(config, headers, issues):
    try:
        specs = parse_new_columns_specs(config)
    except Exception as exc:
        issues.append(_issue("error", "invalid_new_columns", str(exc), path="/config/columns_text"))
        return
    conflict_mode = str(config.get("conflict_mode", "自动改名") or "自动改名")
    if conflict_mode not in {"自动改名", "跳过已有字段", "覆盖已有字段", "存在则报错"}:
        issues.append(_issue("error", "invalid_conflict_mode", f"未知同名字段处理方式：{conflict_mode}", path="/config/conflict_mode"))
    if conflict_mode == "存在则报错":
        duplicated = [name for name, _value in specs if name in headers]
        if duplicated:
            issues.append(_issue("error", "new_column_exists", "字段已存在：" + "、".join(dict.fromkeys(duplicated)), path="/config/columns_text"))


def _validate_replace(config, headers, issues):
    target = str(config.get("target_field", "") or "").strip()
    if not target:
        issues.append(_issue("error", "missing_target_field", "批量替换必须选择目标字段。", path="/config/target_field"))
    elif headers and target not in headers:
        issues.append(_issue("error", "unknown_target_field", f"目标字段不存在：{target}", path="/config/target_field"))

    match_mode = str(config.get("match_mode", "包含") or "包含").strip()
    if match_mode not in REPLACE_MATCH_MODES:
        issues.append(_issue("error", "invalid_match_mode", f"未知匹配方式：{match_mode}", path="/config/match_mode"))
    replace_mode = str(config.get("replace_mode", "局部替换匹配字符串") or "局部替换匹配字符串").strip()
    if replace_mode not in REPLACE_MODES:
        issues.append(_issue("error", "invalid_replace_mode", f"未知替换方式：{replace_mode}", path="/config/replace_mode"))

    match_source = config.get("match_value_source") or config.get("value_source") or "手动输入"
    replace_source = config.get("replace_value_source") or config.get("value_source") or "手动输入"
    _validate_optional_field_source(config, headers, issues, match_source, "match_value_field")
    _validate_optional_field_source(config, headers, issues, replace_source, "replace_value_field")

    if match_mode == "正则匹配" and str(match_source) not in ("列字段", "字段", "当前表字段"):
        pattern = str(config.get("match_value", "") or "")
        if not pattern:
            issues.append(_issue("warning", "empty_regex", "正则匹配值为空，运行时可能匹配所有位置。", path="/config/match_value"))
        else:
            try:
                re.compile(pattern, flags=0 if bool(config.get("case_sensitive", True)) else re.IGNORECASE)
            except re.error as exc:
                issues.append(_issue("error", "invalid_regex", f"正则错误：{exc}", path="/config/match_value"))


def _validate_optional_field_source(config, headers, issues, source, key):
    if str(source) not in ("列字段", "字段", "当前表字段"):
        return
    field = str(config.get(key, "") or "").strip()
    if not field:
        issues.append(_issue("error", "missing_source_field", f"{key} 选择了列字段但未指定字段。", path=f"/config/{key}"))
    elif headers and field not in headers:
        issues.append(_issue("error", "unknown_source_field", f"字段不存在：{field}", path=f"/config/{key}"))


def _validate_merge_columns(config, headers, issues):
    fields = config.get("fields", [])
    if not isinstance(fields, list) or not fields:
        issues.append(_issue("error", "missing_merge_fields", "合并列必须选择至少一个字段。", path="/config/fields"))
        return
    missing = [str(field) for field in fields if headers and str(field) not in headers]
    if missing:
        issues.append(_issue("error", "unknown_merge_fields", "合并字段不存在：" + "、".join(dict.fromkeys(missing)), path="/config/fields"))
    output_field = str(config.get("output_field", "") or "").strip()
    if not output_field:
        issues.append(_issue("warning", "empty_output_field", "未填写输出字段名，将使用默认字段名。", path="/config/output_field"))


def _validate_filter(config, headers, table_names, table_columns, issues):
    conditions = config.get("conditions", [])
    join_rules = config.get("join_rules", [])
    output_fields = config.get("output_fields", [])
    if not isinstance(conditions, list):
        issues.append(_issue("error", "invalid_filter_conditions", "筛选条件必须是列表。", path="/config/conditions"))
        conditions = []
    if not isinstance(join_rules, list):
        issues.append(_issue("error", "invalid_filter_join_rules", "匹配规则必须是列表。", path="/config/join_rules"))
        join_rules = []
    if output_fields is not None and not isinstance(output_fields, list):
        issues.append(_issue("error", "invalid_filter_output_fields", "输出字段必须是列表。", path="/config/output_fields"))
    if not conditions:
        issues.append(_issue("warning", "empty_filter_conditions", "高级筛选没有条件，可能输出全部行。", path="/config/conditions"))
    extra_tables = _filter_extra_tables(config, table_names)
    if extra_tables and not join_rules:
        issues.append(_issue("warning", "missing_filter_join_rules", "已选择副表但没有匹配规则，可能形成全组合。", path="/config/join_rules"))

    available = _filter_available_fields(headers, extra_tables, table_columns)
    for index, cond in enumerate(conditions):
        if not isinstance(cond, dict):
            issues.append(_issue("error", "invalid_filter_condition", "筛选条件必须是 object。", path=f"/config/conditions/{index}"))
            continue
        field = str(cond.get("field", "") or "").strip()
        if not field:
            issues.append(_issue("error", "missing_filter_field", "筛选条件缺少字段。", path=f"/config/conditions/{index}/field"))
        elif available and field not in available:
            issues.append(_issue("error", "unknown_filter_field", f"筛选字段不存在：{field}", path=f"/config/conditions/{index}/field"))
        op = str(cond.get("op", "包含") or "包含")
        if op not in FILTER_CONDITION_OPS:
            issues.append(_issue("error", "invalid_filter_op", f"未知筛选条件：{op}", path=f"/config/conditions/{index}/op"))
        if op == "正则匹配":
            try:
                re.compile(str(cond.get("value", "") or ""))
            except re.error as exc:
                issues.append(_issue("error", "invalid_filter_regex", f"正则错误：{exc}", path=f"/config/conditions/{index}/value"))

    for index, rule in enumerate(join_rules):
        if not isinstance(rule, dict):
            issues.append(_issue("error", "invalid_filter_join_rule", "匹配规则必须是 object。", path=f"/config/join_rules/{index}"))
            continue
        for side in ("left", "right"):
            field = str(rule.get(side, "") or "").strip()
            if not field:
                issues.append(_issue("error", "missing_filter_join_field", f"匹配规则缺少 {side} 字段。", path=f"/config/join_rules/{index}/{side}"))
            elif available and field not in available:
                issues.append(_issue("error", "unknown_filter_join_field", f"匹配字段不存在：{field}", path=f"/config/join_rules/{index}/{side}"))
        op = str(rule.get("op", "等于") or "等于")
        if op not in FILTER_JOIN_OPS:
            issues.append(_issue("error", "invalid_filter_join_op", f"未知匹配方式：{op}", path=f"/config/join_rules/{index}/op"))


def _filter_extra_tables(config, table_names):
    tables = []
    for key in ("selected_tables", "extra_tables", "tables"):
        value = config.get(key)
        if isinstance(value, list):
            tables.extend(str(item) for item in value if str(item).strip())
    for key in ("source_table", "main_table"):
        value = str(config.get(key, "") or "").strip()
        if value and value in table_names and value not in tables:
            tables.append(value)
    return list(dict.fromkeys(tables))


def _filter_available_fields(headers, extra_tables, table_columns):
    available = set(str(header) for header in headers)
    available.update(f"当前表.{header}" for header in headers)
    for table in extra_tables:
        columns = table_columns.get(table, [])
        for column in columns or []:
            available.add(f"{table}.{column}")
    return available


def _result(node_type_id, issues):
    return {
        "ok": not has_error_issues(issues),
        "node_type_id": node_type_id,
        "issues": issues,
        "covered": node_type_id in SUPPORTED_CONFIG_VALIDATION_NODE_IDS,
    }


def _issue(severity, code, message, *, path="", node_index=None):
    return make_issue(severity, code, message, path=path, node_index=node_index, source="config_validation")
