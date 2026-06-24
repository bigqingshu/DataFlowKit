# -*- coding: utf-8 -*-
"""Pure helpers for advanced filter node configuration UI."""

from __future__ import annotations

import copy

from workflow.nodes.filter_plan_nodes import (
    get_plan_filter_output_header_conflicts,
    get_plan_filter_output_headers,
    normalize_filter_condition_value_source,
)
from workflow.advanced_filter_command_service import (
    apply_advanced_filter_command,
    describe_advanced_filter_state,
)


FILTER_CONFIG_CONTEXT_SCHEMA_VERSION = "filter_config_context.v1"
FILTER_OPTIONS_STATE_SCHEMA_VERSION = "filter_options_state.v1"
FILTER_CONFIG_COMMAND_RESULT_SCHEMA_VERSION = "filter_config_command_result.v1"
FILTER_CONFIG_PROTOCOL_FAMILY = "advanced_filter_service"


FILTER_CONFIG_DEFAULTS = {
    "logic": "AND",
    "join_logic": "AND",
    "conditions": list,
    "join_rules": list,
    "extra_tables": list,
    "output_fields": list,
    "result_limit": "5000",
    "max_intermediate": "200000",
    "remove_duplicates": False,
}


def ensure_filter_config_defaults(config):
    for key, default in FILTER_CONFIG_DEFAULTS.items():
        if key in config:
            continue
        config[key] = default() if callable(default) else default
    return config


def build_filter_selectable_tables(db_tables, transit_table_names):
    tables = list(db_tables or [])
    tables.extend(f"中转:{name}" for name in sorted(transit_table_names or []))
    return tables


def build_filter_available_fields(headers, extra_tables=None, table_columns=None, transit_context=None):
    fields = [f"当前表.{header}" for header in (headers or [])]
    table_columns = table_columns or {}
    transit_tables = (transit_context or {}).get("transit_tables", {}) or {}
    for table in extra_tables or []:
        table_name = str(table or "").strip()
        if not table_name:
            continue
        columns = []
        if table_name.startswith("中转:"):
            transit_name = table_name.split(":", 1)[1]
            item = transit_tables.get(transit_name, {}) if isinstance(transit_tables, dict) else {}
            columns = item.get("headers", []) if isinstance(item, dict) else []
        else:
            columns = table_columns.get(table_name, []) if isinstance(table_columns, dict) else []
        for column in columns or []:
            text = str(column or "").strip()
            if text:
                fields.append(f"{table_name}.{text}")
    return fields


def describe_filter_config_context(config, headers, *, table_names=None, table_columns=None, transit_context=None):
    config_copy = ensure_filter_config_defaults(copy.deepcopy(config or {}))
    extra_tables = list(config_copy.get("extra_tables") or [])
    available_fields = build_filter_available_fields(
        headers,
        extra_tables,
        table_columns=table_columns,
        transit_context=transit_context,
    )
    options_state = build_filter_options_state(
        config_copy,
        headers,
        available_fields,
        transit_context=transit_context,
    )
    return {
        "ok": True,
        "schema_version": FILTER_CONFIG_CONTEXT_SCHEMA_VERSION,
        "protocol_family": FILTER_CONFIG_PROTOCOL_FAMILY,
        "node_type_id": "core.filter",
        "service_schema": "advanced_filter_service.v1",
        "state_schema": "advanced_filter_state.v1",
        "options_state_schema": FILTER_OPTIONS_STATE_SCHEMA_VERSION,
        "config": config_copy,
        "headers": list(headers or []),
        "table_names": list(table_names or []),
        "table_columns": copy.deepcopy(table_columns or {}),
        "available_fields": available_fields,
        "selected_tables": list(options_state.get("selected_tables") or []),
        "field_state": copy.deepcopy(options_state.get("field_state") or {}),
        "config_state": copy.deepcopy(options_state.get("config_state") or {}),
        "risk_state": copy.deepcopy(options_state.get("risk_state") or {}),
        "output_text": str(options_state.get("output_text") or ""),
        "options_state": options_state,
    }


def filter_condition_to_row(cond):
    cond = cond or {}
    return (
        cond.get("field", ""),
        cond.get("op", ""),
        normalize_filter_condition_value_source(cond),
        cond.get("value", ""),
    )


def filter_conditions_to_rows(conditions):
    return [filter_condition_to_row(cond) for cond in (conditions or []) if isinstance(cond, dict)]


def filter_condition_from_row(row):
    values = list(row or [])
    while len(values) < 4:
        values.append("")
    field, op, source, value = values[:4]
    return {
        "field": field,
        "op": op,
        "value_source": normalize_filter_condition_value_source({"value_source": source}),
        "value": value,
    }


def filter_conditions_from_rows(rows):
    return [filter_condition_from_row(row) for row in (rows or [])]


def append_filter_condition_row(rows, field, op, value_source, value):
    result = [tuple(row) for row in (rows or [])]
    condition = filter_condition_from_row((field, op, value_source, value))
    result.append((
        condition["field"],
        condition["op"],
        condition["value_source"],
        condition["value"],
    ))
    return result


def build_filter_config_service_state(config, headers, all_fields):
    config = ensure_filter_config_defaults(config or {})
    fields = list(all_fields or [])
    return describe_advanced_filter_state({
        "main_table": "当前表",
        "selected_tables": ["当前表"] + list(config.get("extra_tables", []) or []),
        "tables_cache": ["当前表"] + list(config.get("extra_tables", []) or []),
        "columns_by_table": _filter_fields_to_columns_by_table(fields),
        "field_display_cache": fields,
        "conditions": config.get("conditions", []),
        "join_rules": config.get("join_rules", []),
        "output_fields": config.get("output_fields", []),
        "logic": config.get("logic", "AND"),
        "join_logic": config.get("join_logic", "AND"),
        "result_limit": config.get("result_limit", "5000"),
        "max_intermediate": config.get("max_intermediate", "200000"),
        "preview_headers": list(headers or []),
    })


def build_filter_options_state(config, headers, all_fields, transit_context=None):
    config = ensure_filter_config_defaults(config or {})
    headers = list(headers or [])
    all_fields = list(all_fields or [])
    extra_tables = list(config.get("extra_tables", []) or [])
    field_state = build_filter_field_refresh_state(
        headers,
        all_fields,
        value_source="字段值" if str(config.get("value_source", "")).strip() == "字段值" else "固定值",
        selected_output_fields=config.get("output_fields", []),
    )
    output_text = build_filter_actual_output_text(
        config.get("output_fields", []),
        headers,
        all_fields,
        config.get("extra_tables", []),
    )
    state = build_filter_config_service_state(config, headers, all_fields)
    selected_tables = state.get("selected_tables", [])
    return {
        "config_state": state,
        "field_state": field_state,
        "output_text": output_text,
        "selected_tables": selected_tables,
        "all_fields": all_fields,
        "headers": headers,
        "extra_tables": extra_tables,
        "transit_context": transit_context or {"transit_tables": {}},
        "risk_state": build_filter_risk_display_state(
            _build_filter_risk_warnings(headers, extra_tables, config, transit_context),
        ),
    }


def apply_filter_config_service_command(config, headers, all_fields, command):
    state = build_filter_config_service_state(config, headers, all_fields)
    return apply_advanced_filter_command(state, command)


def apply_filter_config_command(config, headers, all_fields, command, *, transit_context=None):
    """Apply a UI-neutral command to an advanced-filter node config."""

    config_copy = ensure_filter_config_defaults(copy.deepcopy(config or {}))
    before = copy.deepcopy(config_copy)
    issues = []
    if not isinstance(command, dict):
        issues.append(_filter_config_issue("error", "invalid_command", "command 必须是 object。", path="/command"))
        return _filter_config_command_result(config_copy, headers, all_fields, "", False, issues, transit_context)

    command_type = str(command.get("type") or command.get("command") or "").strip()
    if not command_type:
        issues.append(_filter_config_issue("error", "missing_command_type", "command 缺少 type。", path="/command/type"))
        return _filter_config_command_result(config_copy, headers, all_fields, command_type, False, issues, transit_context)

    service_result = None
    if command_type == "add_condition":
        field = str(command.get("field") or "").strip()
        op = str(command.get("op") or command.get("operator") or "等于").strip()
        value = command.get("value", "")
        service_result = apply_filter_config_service_command(config_copy, headers, all_fields, {
            "type": "add_condition",
            "field": field,
            "op": op,
            "value": value,
            "allow_empty_value": bool(command.get("allow_empty_value")),
        })
        if service_result.get("ok"):
            config_copy["conditions"] = list(config_copy.get("conditions") or [])
            config_copy["conditions"].append({
                "field": field,
                "op": op,
                "value_source": normalize_filter_condition_value_source(command),
                "value": value,
            })

    elif command_type == "delete_conditions":
        rows = filter_conditions_to_rows(config_copy.get("conditions") or [])
        service_result = apply_filter_config_service_command(config_copy, headers, all_fields, {
            "type": "delete_conditions",
            "indexes": command.get("indexes"),
        })
        if service_result.get("ok"):
            config_copy["conditions"] = filter_conditions_from_rows(
                delete_filter_rows_by_indexes(rows, _int_list(command.get("indexes")))
            )

    elif command_type == "clear_conditions":
        service_result = apply_filter_config_service_command(config_copy, headers, all_fields, {"type": "clear_conditions"})
        if service_result.get("ok"):
            config_copy["conditions"] = []

    elif command_type == "add_join_rule":
        left = str(command.get("left") or "").strip()
        op = str(command.get("op") or command.get("operator") or "等于").strip()
        right_table = str(command.get("right_table") or "").strip()
        right = str(command.get("right") or "").strip()
        service_right = f"{right_table}.{right}" if right_table and right and "." not in right else right
        service_result = apply_filter_config_service_command(config_copy, headers, all_fields, {
            "type": "add_join_rule",
            "left": left,
            "op": op,
            "right": service_right,
            "allow_same_field": bool(command.get("allow_same_field")),
        })
        if service_result.get("ok"):
            config_copy["join_rules"] = list(config_copy.get("join_rules") or [])
            config_copy["join_rules"].append(filter_join_rule_from_row((left, op, right_table, right)))

    elif command_type == "delete_join_rules":
        rows = filter_join_rules_to_rows(config_copy.get("join_rules") or [])
        service_result = apply_filter_config_service_command(config_copy, headers, all_fields, {
            "type": "delete_join_rules",
            "indexes": command.get("indexes"),
        })
        if service_result.get("ok"):
            config_copy["join_rules"] = filter_join_rules_from_rows(
                delete_filter_rows_by_indexes(rows, _int_list(command.get("indexes")))
            )

    elif command_type == "clear_join_rules":
        service_result = apply_filter_config_service_command(config_copy, headers, all_fields, {"type": "clear_join_rules"})
        if service_result.get("ok"):
            config_copy["join_rules"] = []

    elif command_type in {
        "add_output_fields",
        "add_all_output_fields",
        "remove_output_fields",
        "clear_output_fields",
    }:
        service_result = apply_filter_config_service_command(config_copy, headers, all_fields, command)
        if service_result.get("ok"):
            config_copy["output_fields"] = list((service_result.get("state") or {}).get("output_fields") or [])

    else:
        issues.append(_filter_config_issue(
            "error",
            "unknown_filter_config_command",
            f"未知高级筛选配置 command：{command_type}",
            path="/command/type",
        ))
        return _filter_config_command_result(config_copy, headers, all_fields, command_type, False, issues, transit_context)

    issues.extend(copy.deepcopy((service_result or {}).get("issues") or []))
    ok = bool((service_result or {}).get("ok", False))
    changed = before != config_copy
    return _filter_config_command_result(
        config_copy,
        headers,
        all_fields,
        command_type,
        changed,
        issues,
        transit_context,
        ok=ok,
        requires_confirmation=bool((service_result or {}).get("requires_confirmation")),
        service_result=service_result,
    )


def append_filter_condition_row_via_service(rows, config, headers, all_fields, field, op, value_source, value):
    config_copy = dict(config or {})
    existing_conditions = filter_conditions_from_rows(rows)
    config_copy["conditions"] = existing_conditions
    result = apply_filter_config_service_command(
        config_copy,
        headers,
        all_fields,
        {
            "type": "add_condition",
            "field": field,
            "op": op,
            "value": value,
            "allow_empty_value": True,
        },
    )
    conditions = list(existing_conditions)
    if result["ok"]:
        conditions.append({
            "field": field,
            "op": op,
            "value_source": normalize_filter_condition_value_source({"value_source": value_source}),
            "value": value,
        })
    return {
        "ok": result["ok"],
        "rows": filter_conditions_to_rows(conditions),
        "conditions": conditions,
        "issues": result.get("issues", []),
    }


def delete_filter_condition_rows_via_service(rows, config, headers, all_fields, selected_indexes):
    config_copy = dict(config or {})
    config_copy["conditions"] = filter_conditions_from_rows(rows)
    result = apply_filter_config_service_command(
        config_copy,
        headers,
        all_fields,
        {
            "type": "delete_conditions",
            "indexes": selected_indexes,
        },
    )
    remaining_rows = delete_filter_rows_by_indexes(rows, selected_indexes)
    conditions = filter_conditions_from_rows(remaining_rows)
    return {
        "ok": result["ok"],
        "rows": filter_conditions_to_rows(conditions),
        "conditions": conditions,
        "issues": result.get("issues", []),
    }


def delete_filter_rows_by_indexes(rows, selected_indexes):
    selected = set(selected_indexes or [])
    return [tuple(row) for index, row in enumerate(rows or []) if index not in selected]


def parse_treeview_column_index(column_id, column_count):
    try:
        index = int(str(column_id or "").replace("#", "", 1)) - 1
    except Exception:
        return None
    if index < 0 or index >= int(column_count):
        return None
    return index


def normalize_treeview_row_values(values, column_count):
    normalized = list(values or [])
    while len(normalized) < int(column_count):
        normalized.append("")
    return normalized


def build_treeview_cell_edit_state(values, column_id, column_count):
    index = parse_treeview_column_index(column_id, column_count)
    if index is None:
        return None
    normalized = normalize_treeview_row_values(values, column_count)
    return {
        "column_index": index,
        "values": normalized,
        "text": normalized[index],
    }


def apply_treeview_cell_edit(values, column_index, new_value, column_count):
    if column_index is None or column_index < 0 or column_index >= int(column_count):
        return None
    normalized = normalize_treeview_row_values(values, column_count)
    normalized[column_index] = new_value
    return normalized


def filter_join_rule_to_row(rule):
    rule = rule or {}
    right_table = rule.get("right_table", "")
    right = rule.get("right", "")
    if not right_table and "." in str(right or ""):
        right_table, _, right = str(right).partition(".")
    return (
        rule.get("left", ""),
        rule.get("op", "等于"),
        right_table,
        right,
    )


def filter_join_rules_to_rows(join_rules):
    return [filter_join_rule_to_row(rule) for rule in (join_rules or []) if isinstance(rule, dict)]


def filter_join_rule_from_row(row):
    values = list(row or [])
    while len(values) < 4:
        values.append("")
    left, op, right_table, right = values[:4]
    payload = {"left": left, "op": op, "right": right}
    if right_table:
        payload["right_table"] = right_table
        if right and "." not in str(right):
            payload["right"] = f"{right_table}.{right}"
    return payload


def filter_join_rules_from_rows(rows):
    return [filter_join_rule_from_row(row) for row in (rows or [])]


def append_filter_join_rule_row(rows, left, op, right):
    result = [tuple(row) for row in (rows or [])]
    rule = filter_join_rule_from_row((left, op, "", right))
    result.append(filter_join_rule_to_row(rule))
    return result


def append_filter_join_rule_row_via_service(rows, config, headers, all_fields, left, op, right):
    config_copy = dict(config or {})
    config_copy["join_rules"] = filter_join_rules_from_rows(rows)
    result = apply_filter_config_service_command(
        config_copy,
        headers,
        all_fields,
        {
            "type": "add_join_rule",
            "left": left,
            "op": op,
            "right": right,
            "allow_same_field": True,
        },
    )
    rows = filter_join_rules_to_rows(result.get("state", {}).get("join_rules") or [])
    join_rules = filter_join_rules_from_rows(rows)
    return {
        "ok": result["ok"],
        "rows": rows,
        "join_rules": join_rules,
        "issues": result.get("issues", []),
    }


def delete_filter_join_rule_rows_via_service(rows, config, headers, all_fields, selected_indexes):
    config_copy = dict(config or {})
    config_copy["join_rules"] = filter_join_rules_from_rows(rows)
    result = apply_filter_config_service_command(
        config_copy,
        headers,
        all_fields,
        {
            "type": "delete_join_rules",
            "indexes": selected_indexes,
        },
    )
    rows = filter_join_rules_to_rows(result.get("state", {}).get("join_rules") or [])
    join_rules = filter_join_rules_from_rows(rows)
    return {
        "ok": result["ok"],
        "rows": rows,
        "join_rules": join_rules,
        "issues": result.get("issues", []),
    }


def choose_filter_actual_output_lookup_fields(selected_fields, headers, all_fields, extra_tables):
    selected_fields = list(selected_fields or [])
    if selected_fields:
        return selected_fields
    if extra_tables:
        return list(all_fields or [])
    return list(headers or [])


def build_filter_field_refresh_state(headers, all_fields, value_source="固定值", selected_output_fields=None):
    all_values = list(all_fields or [])
    current_values = [f"当前表.{header}" for header in (headers or [])]
    first_any = all_values[0] if all_values else ""
    first_current = current_values[0] if current_values else first_any
    first_external = next((field for field in all_values if not str(field).startswith("当前表.")), first_any)
    normalized_value_source = normalize_filter_condition_value_source({"value_source": value_source})
    return {
        "all_values": all_values,
        "current_values": current_values,
        "first_any": first_any,
        "first_current": first_current,
        "first_external": first_external,
        "value_choices": all_values if normalized_value_source == "字段值" else [],
        "value_fallback": first_any if normalized_value_source == "字段值" else "",
        "selected_output": set(selected_output_fields or []),
        "value_source": normalized_value_source,
    }


def build_filter_condition_input_state(all_fields, value_source="固定值", current_value=""):
    fields = list(all_fields or [])
    source = normalize_filter_condition_value_source({"value_source": value_source})
    return {
        "field_default": fields[0] if fields else "",
        "value_source": source,
        "value_choices": fields if source == "字段值" else [],
        "value_default": fields[0] if source == "字段值" and not str(current_value or "").strip() and fields else current_value,
    }


def build_filter_join_input_state(current_fields, all_fields):
    current_values = list(current_fields or [])
    all_values = list(all_fields or [])
    first_any = all_values[0] if all_values else ""
    right_default = next((field for field in all_values if not str(field).startswith("当前表.")), first_any)
    return {
        "left_default": current_values[0] if current_values else first_any,
        "right_default": right_default,
    }


def filter_dedupe_button_text(enabled):
    return "去除重复内容:开" if bool(enabled) else "去除重复内容:关"


def toggle_filter_dedupe_config(config):
    config["remove_duplicates"] = not bool(config.get("remove_duplicates", False))
    return config["remove_duplicates"]


def build_filter_risk_display_state(warnings):
    warnings = list(warnings or [])
    if warnings:
        return {
            "text": "风险提示：" + "；".join(str(item) for item in warnings),
            "foreground": "#9a5a00",
        }
    return {
        "text": "状态：当前多表筛选未发现明显全组合风险。",
        "foreground": "gray",
    }


def build_filter_field_refresh_status(extra_table_count, field_count):
    return f"高级筛选字段已局部刷新：{int(extra_table_count)} 个副表，{int(field_count)} 个可用字段。"


def build_filter_actual_output_text(selected_fields, headers, all_fields, extra_tables, display_limit=12, conflict_limit=6):
    lookup_fields = choose_filter_actual_output_lookup_fields(
        selected_fields,
        headers,
        all_fields,
        extra_tables,
    )
    actual_headers = get_plan_filter_output_headers(lookup_fields, headers)
    conflicts = get_plan_filter_output_header_conflicts(lookup_fields, headers)
    display = actual_headers[:display_limit]
    suffix = f" 等 {len(actual_headers)} 个字段" if len(actual_headers) > len(display) else ""
    text = "实际输出字段：" + ("、".join(display) + suffix if display else "无")
    if conflicts:
        text += "；重名自动编号：" + "、".join(conflicts[:conflict_limit])
    return text


def select_all_filter_output_fields(fields):
    result = apply_advanced_filter_command(
        describe_advanced_filter_state({
            "field_display_cache": list(fields or []),
            "output_fields": [],
        }),
        {"type": "add_all_output_fields"},
    )
    return list(result.get("state", {}).get("output_fields") or [])


def invert_filter_output_fields(fields, selected_fields):
    selected = set(selected_fields or [])
    return [field for field in (fields or []) if field not in selected]


def invert_filter_output_fields_by_indexes(fields, selected_indexes):
    fields = list(fields or [])
    result = apply_advanced_filter_command(
        describe_advanced_filter_state({
            "field_display_cache": fields,
            "output_fields": fields,
        }),
        {
            "type": "remove_output_fields",
            "indexes": selected_indexes,
        },
    )
    return list(result.get("state", {}).get("output_fields") or [])


def select_current_table_filter_output_fields(fields):
    return [field for field in (fields or []) if str(field).startswith("当前表.")]


def _filter_fields_to_columns_by_table(fields):
    columns_by_table = {}
    for field in fields or []:
        table, sep, column = str(field).partition(".")
        if not sep:
            table = "当前表"
            column = str(field)
        columns_by_table.setdefault(table, [])
        if column and column not in columns_by_table[table]:
            columns_by_table[table].append(column)
    return columns_by_table


def _build_filter_risk_warnings(headers, extra_tables, config, transit_context):
    transit_context = transit_context or {"transit_tables": {}}
    warnings = []
    if extra_tables and not headers:
        warnings.append("当前表没有字段，副表匹配可能无法生成结果。")
    if len(extra_tables) > 3:
        warnings.append("副表数量较多时，可能产生较大的组合开销。")
    if not extra_tables and config.get("join_rules"):
        warnings.append("已配置匹配规则，但没有选择副表。")
    return warnings


def _filter_config_command_result(
    config,
    headers,
    all_fields,
    command_type,
    changed,
    issues,
    transit_context,
    *,
    ok=None,
    requires_confirmation=False,
    service_result=None,
):
    has_error = any(str(issue.get("severity") or "").lower() == "error" for issue in issues or [])
    if ok is None:
        ok = not has_error and not requires_confirmation
    options_state = build_filter_options_state(
        config,
        headers,
        all_fields,
        transit_context=transit_context,
    )
    return {
        "ok": bool(ok) and not has_error and not requires_confirmation,
        "schema_version": FILTER_CONFIG_COMMAND_RESULT_SCHEMA_VERSION,
        "protocol_family": FILTER_CONFIG_PROTOCOL_FAMILY,
        "node_type_id": "core.filter",
        "command": command_type,
        "changed": bool(changed),
        "config": ensure_filter_config_defaults(copy.deepcopy(config or {})),
        "options_state": options_state,
        "issues": list(issues or []),
        "requires_confirmation": bool(requires_confirmation),
        "service_result": copy.deepcopy(service_result or {}),
    }


def _filter_config_issue(severity, code, message, *, path=""):
    return {
        "severity": str(severity or "warning"),
        "code": str(code or ""),
        "message": str(message or ""),
        "path": str(path or ""),
        "source": FILTER_CONFIG_PROTOCOL_FAMILY,
    }


def _int_list(values):
    if values is None:
        return []
    if isinstance(values, int):
        return [values]
    result = []
    for value in values or []:
        try:
            result.append(int(value))
        except Exception:
            continue
    return result
