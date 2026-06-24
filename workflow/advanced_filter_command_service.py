# -*- coding: utf-8 -*-
"""UI-neutral command service for the advanced filter editor."""

from __future__ import annotations

import copy

from engine.issue_schema import has_error_issues, make_issue
from workflow.advanced_filter_window_logic import (
    add_advanced_filter_condition,
    add_advanced_filter_join_rule,
    add_advanced_filter_output_fields,
    add_all_advanced_filter_output_fields,
    build_advanced_filter_field_display_cache,
    build_advanced_filter_main_preview_snapshot,
    build_advanced_filter_preview_rows,
    build_advanced_filter_result_records,
    build_advanced_filter_template_data,
    clear_advanced_filter_items,
    dedupe_advanced_filter_preview_rows,
    filter_advanced_filter_valid_state,
    get_advanced_filter_output_fields,
    normalize_advanced_filter_template_data,
    remove_advanced_filter_items_by_indexes,
    remove_advanced_filter_output_fields,
    select_advanced_filter_combo_defaults,
    select_advanced_filter_template_tables,
)


ADVANCED_FILTER_STATE_SCHEMA_VERSION = "advanced_filter_state.v1"
ADVANCED_FILTER_COMMAND_SCHEMA_VERSION = "advanced_filter_command.v1"
ADVANCED_FILTER_SERVICE_SCHEMA_VERSION = "advanced_filter_service.v1"
ADVANCED_FILTER_PROTOCOL_FAMILY = "advanced_filter_service"

EMPTY_VALUE_OPERATORS = {"为空", "不为空"}


def describe_advanced_filter_service():
    return {
        "schema_version": ADVANCED_FILTER_SERVICE_SCHEMA_VERSION,
        "protocol_family": ADVANCED_FILTER_PROTOCOL_FAMILY,
        "state_schema": ADVANCED_FILTER_STATE_SCHEMA_VERSION,
        "command_schema": ADVANCED_FILTER_COMMAND_SCHEMA_VERSION,
        "commands": [
            "refresh_fields",
            "filter_valid_state",
            "add_condition",
            "delete_conditions",
            "clear_conditions",
            "add_join_rule",
            "delete_join_rules",
            "clear_join_rules",
            "add_output_fields",
            "add_all_output_fields",
            "remove_output_fields",
            "clear_output_fields",
            "build_preview",
            "dedupe_preview",
            "build_main_preview_snapshot",
            "export_template",
            "apply_template",
        ],
    }


def describe_advanced_filter_state(state=None, *, selected_tables=None, columns_by_table=None):
    """Return a normalized advanced-filter editor state for any UI shell."""

    payload = copy.deepcopy(state or {})
    if selected_tables is not None:
        payload["selected_tables"] = selected_tables
    if columns_by_table is not None:
        payload["columns_by_table"] = columns_by_table
    return _normalize_state(payload)


def apply_advanced_filter_command(state, command):
    """Apply a UI-neutral edit command to an advanced-filter state copy."""

    issues = []
    current = _normalize_state(state)
    if not isinstance(command, dict):
        issues.append(_issue("error", "invalid_command", "command 必须是 object。", path="/command"))
        return _result(current, False, issues, "", requires_confirmation=False)

    command_type = str(command.get("type") or command.get("command") or "").strip()
    if not command_type:
        issues.append(_issue("error", "missing_command_type", "command 缺少 type。", path="/command/type"))
        return _result(current, False, issues, command_type, requires_confirmation=False)

    changed = False
    requires_confirmation = False

    if command_type == "refresh_fields":
        if "selected_tables" in command:
            current["selected_tables"] = _string_list(command.get("selected_tables"))
        if "columns_by_table" in command:
            current["columns_by_table"] = _dict_of_string_lists(command.get("columns_by_table"))
        current["field_display_cache"] = build_advanced_filter_field_display_cache(
            current["selected_tables"],
            current["columns_by_table"],
        )
        current = _normalize_state(current)
        current = _filter_valid_items(current)
        changed = True

    elif command_type == "filter_valid_state":
        before = _editable_state_slice(current)
        current = _filter_valid_items(current)
        changed = before != _editable_state_slice(current)

    elif command_type == "add_condition":
        field = str(command.get("field") or "").strip()
        op = str(command.get("op") or command.get("operator") or "等于").strip()
        value = command.get("value", "")
        if not field:
            issues.append(_issue("error", "missing_condition_field", "请选择筛选字段。", path="/command/field"))
        elif op not in EMPTY_VALUE_OPERATORS and value == "" and not bool(command.get("allow_empty_value")):
            issues.append(_issue(
                "warning",
                "empty_condition_value_requires_confirmation",
                "当前条件值为空，需要确认后再添加。",
                path="/command/value",
            ))
            requires_confirmation = True
        else:
            current["conditions"] = add_advanced_filter_condition(current["conditions"], field, op, value)
            changed = True

    elif command_type == "delete_conditions":
        before = current["conditions"]
        current["conditions"] = remove_advanced_filter_items_by_indexes(
            current["conditions"],
            _int_list(command.get("indexes")),
        )
        changed = before != current["conditions"]

    elif command_type == "clear_conditions":
        changed = bool(current["conditions"])
        current["conditions"] = clear_advanced_filter_items()

    elif command_type == "add_join_rule":
        left = str(command.get("left") or "").strip()
        op = str(command.get("op") or command.get("operator") or "等于").strip()
        right = str(command.get("right") or "").strip()
        if not left or not right:
            issues.append(_issue("error", "missing_join_field", "请选择左右匹配字段。", path="/command"))
        elif left == right and not bool(command.get("allow_same_field")):
            issues.append(_issue(
                "warning",
                "same_join_field_requires_confirmation",
                "左右字段相同，需要确认后再添加。",
                path="/command",
            ))
            requires_confirmation = True
        else:
            current["join_rules"] = add_advanced_filter_join_rule(current["join_rules"], left, op, right)
            changed = True

    elif command_type == "delete_join_rules":
        before = current["join_rules"]
        current["join_rules"] = remove_advanced_filter_items_by_indexes(
            current["join_rules"],
            _int_list(command.get("indexes")),
        )
        changed = before != current["join_rules"]

    elif command_type == "clear_join_rules":
        changed = bool(current["join_rules"])
        current["join_rules"] = clear_advanced_filter_items()

    elif command_type == "add_output_fields":
        before = current["output_fields"]
        current["output_fields"] = add_advanced_filter_output_fields(
            current["output_fields"],
            current["field_display_cache"],
            _int_list(command.get("indexes")),
        )
        changed = before != current["output_fields"]

    elif command_type == "add_all_output_fields":
        before = current["output_fields"]
        current["output_fields"] = add_all_advanced_filter_output_fields(
            current["output_fields"],
            current["field_display_cache"],
        )
        changed = before != current["output_fields"]

    elif command_type == "remove_output_fields":
        before = current["output_fields"]
        current["output_fields"] = remove_advanced_filter_output_fields(
            current["output_fields"],
            _int_list(command.get("indexes")),
        )
        changed = before != current["output_fields"]

    elif command_type == "clear_output_fields":
        changed = bool(current["output_fields"])
        current["output_fields"] = []

    elif command_type == "build_preview":
        fields = get_advanced_filter_output_fields(
            current["output_fields"],
            current["field_display_cache"],
        )
        if not fields:
            issues.append(_issue("error", "missing_output_fields", "没有可输出字段，请先选择数据源。", path="/state/output_fields"))
        else:
            try:
                records = build_advanced_filter_result_records(
                    current["selected_tables"],
                    _record_map(command.get("table_records_map")),
                    conditions=current["conditions"],
                    condition_logic=current["logic"],
                    join_rules=current["join_rules"],
                    join_logic=current["join_logic"],
                    result_limit=_positive_int(current["result_limit"], 5000),
                    max_intermediate=_positive_int(current["max_intermediate"], 200000),
                )
                current["preview_headers"] = fields
                current["preview_rows"] = build_advanced_filter_preview_rows(records, fields)
                changed = True
            except Exception as exc:
                issues.append(_issue("error", "build_preview_failed", str(exc), path="/command/table_records_map"))

    elif command_type == "dedupe_preview":
        if not current["preview_headers"]:
            issues.append(_issue("error", "missing_preview", "请先预览结果。", path="/state/preview_headers"))
        else:
            deduped = dedupe_advanced_filter_preview_rows(current["preview_rows"])
            current["preview_rows"] = deduped["rows"]
            changed = bool(deduped["removed"])

    elif command_type == "build_main_preview_snapshot":
        if not current["preview_headers"]:
            issues.append(_issue("error", "missing_preview", "请先预览结果。", path="/state/preview_headers"))

    elif command_type == "export_template":
        pass

    elif command_type == "apply_template":
        template_data = command.get("template") or command.get("data") or {}
        selected_tables = select_advanced_filter_template_tables(
            template_data,
            current["tables_cache"],
        )
        current["selected_tables"] = selected_tables
        if template_data.get("main_table"):
            current["main_table"] = str(template_data.get("main_table") or "")
        current["field_display_cache"] = build_advanced_filter_field_display_cache(
            selected_tables,
            current["columns_by_table"],
        )
        normalized = normalize_advanced_filter_template_data(
            template_data,
            current["tables_cache"],
            current["field_display_cache"],
            current_save_table=current["save_table"],
        )
        current.update({
            "selected_tables": normalized["selected_tables"],
            "conditions": normalized["conditions"],
            "join_rules": normalized["join_rules"],
            "output_fields": normalized["output_fields"],
            "logic": normalized["logic"],
            "join_logic": normalized["join_logic"],
            "result_limit": normalized["result_limit"],
            "max_intermediate": normalized["max_intermediate"],
            "save_table": normalized["save_table"],
        })
        changed = True

    else:
        issues.append(_issue("error", "unknown_command", f"未知高级筛选 command：{command_type}", path="/command/type"))

    current = _normalize_state(current)
    return _result(
        current,
        changed,
        issues,
        command_type,
        requires_confirmation=requires_confirmation,
        extra=_command_extra(current, command_type),
    )


def _normalize_state(state):
    state = copy.deepcopy(state or {})
    selected_tables = _string_list(state.get("selected_tables"))
    columns_by_table = _dict_of_string_lists(
        state.get("columns_by_table")
        if state.get("columns_by_table") is not None
        else state.get("columns_cache")
    )
    field_display_cache = _string_list(state.get("field_display_cache"))
    if not field_display_cache:
        field_display_cache = build_advanced_filter_field_display_cache(selected_tables, columns_by_table)

    defaults = select_advanced_filter_combo_defaults(
        field_display_cache,
        _string_value(state.get("filter_field")),
        _string_value(state.get("join_left")),
        _string_value(state.get("join_right")),
    )

    return {
        "schema_version": ADVANCED_FILTER_STATE_SCHEMA_VERSION,
        "main_table": _string_value(state.get("main_table")),
        "tables_cache": _string_list(state.get("tables_cache")),
        "selected_tables": selected_tables,
        "columns_by_table": columns_by_table,
        "field_display_cache": field_display_cache,
        "filter_field": defaults["filter_field"],
        "join_left": defaults["join_left"],
        "join_right": defaults["join_right"],
        "conditions": _condition_list(state.get("conditions")),
        "join_rules": _join_rule_list(state.get("join_rules")),
        "output_fields": _string_list(state.get("output_fields")),
        "logic": _string_value(state.get("logic"), "AND"),
        "join_logic": _string_value(state.get("join_logic"), "AND"),
        "result_limit": _string_value(state.get("result_limit"), "5000"),
        "max_intermediate": _string_value(state.get("max_intermediate"), "200000"),
        "save_table": _string_value(state.get("save_table")),
        "preview_headers": _string_list(state.get("preview_headers")),
        "preview_rows": _row_list(state.get("preview_rows")),
    }


def _filter_valid_items(state):
    current = _normalize_state(state)
    filtered = filter_advanced_filter_valid_state(
        current["conditions"],
        current["join_rules"],
        current["output_fields"],
        current["field_display_cache"],
    )
    current["conditions"] = filtered["conditions"]
    current["join_rules"] = filtered["join_rules"]
    current["output_fields"] = filtered["output_fields"]
    return _normalize_state(current)


def _editable_state_slice(state):
    return {
        "conditions": copy.deepcopy(state.get("conditions") or []),
        "join_rules": copy.deepcopy(state.get("join_rules") or []),
        "output_fields": list(state.get("output_fields") or []),
    }


def _result(state, changed, issues, command_type, *, requires_confirmation, extra=None):
    payload = {
        "ok": not has_error_issues(issues) and not requires_confirmation,
        "changed": bool(changed),
        "command": command_type,
        "state": copy.deepcopy(state),
        "issues": issues,
        "requires_confirmation": bool(requires_confirmation),
    }
    payload.update(extra or {})
    return payload


def _command_extra(state, command_type):
    if command_type == "dedupe_preview":
        return {
            "preview": {
                "headers": list(state.get("preview_headers") or []),
                "rows": _row_list(state.get("preview_rows")),
                "row_count": len(state.get("preview_rows") or []),
            }
        }
    if command_type == "build_preview":
        return {
            "preview": {
                "headers": list(state.get("preview_headers") or []),
                "rows": _row_list(state.get("preview_rows")),
                "row_count": len(state.get("preview_rows") or []),
            }
        }
    if command_type == "build_main_preview_snapshot":
        return {
            "main_preview_snapshot": build_advanced_filter_main_preview_snapshot(
                state.get("preview_headers") or [],
                state.get("preview_rows") or [],
            )
        }
    if command_type == "export_template":
        return {
            "template": build_advanced_filter_template_data(
                state.get("main_table", ""),
                state.get("selected_tables", []),
                state.get("conditions", []),
                state.get("logic", "AND"),
                state.get("join_logic", "AND"),
                state.get("join_rules", []),
                state.get("output_fields", []),
                state.get("result_limit", "5000"),
                state.get("max_intermediate", "200000"),
                state.get("save_table", ""),
            )
        }
    return {}


def _issue(severity, code, message, *, path=""):
    return make_issue(
        severity,
        code,
        message,
        path=path,
        source=ADVANCED_FILTER_PROTOCOL_FAMILY,
    )


def _string_value(value, default=""):
    if value is None:
        return str(default)
    return str(value)


def _string_list(values):
    if values is None:
        return []
    if isinstance(values, (str, bytes)):
        return [str(values)]
    result = []
    for value in values:
        text = str(value)
        if text:
            result.append(text)
    return result


def _int_list(values):
    if values is None:
        return []
    if isinstance(values, int):
        return [values]
    result = []
    for value in values:
        try:
            result.append(int(value))
        except Exception:
            continue
    return result


def _positive_int(value, default):
    try:
        parsed = int(str(value).strip())
        if parsed > 0:
            return parsed
    except Exception:
        pass
    return default


def _row_list(values):
    result = []
    for row in values or []:
        if isinstance(row, (str, bytes)):
            result.append([str(row)])
        else:
            try:
                result.append(list(row))
            except Exception:
                result.append([row])
    return result


def _record_map(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for table, records in value.items():
        result[str(table)] = [
            dict(record)
            for record in records or []
            if isinstance(record, dict)
        ]
    return result


def _dict_of_string_lists(value):
    if not isinstance(value, dict):
        return {}
    return {
        str(key): _string_list(values)
        for key, values in value.items()
    }


def _condition_list(values):
    result = []
    for item in values or []:
        if not isinstance(item, dict):
            continue
        result.append({
            "field": _string_value(item.get("field")),
            "op": _string_value(item.get("op")),
            "value": item.get("value", ""),
        })
    return result


def _join_rule_list(values):
    result = []
    for item in values or []:
        if not isinstance(item, dict):
            continue
        result.append({
            "left": _string_value(item.get("left")),
            "op": _string_value(item.get("op")),
            "right": _string_value(item.get("right")),
        })
    return result
