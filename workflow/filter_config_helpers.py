# -*- coding: utf-8 -*-
"""Pure helpers for advanced filter node configuration UI."""

from workflow.nodes.data_nodes import (
    get_plan_filter_output_header_conflicts,
    get_plan_filter_output_headers,
    normalize_filter_condition_value_source,
)


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
    return (
        rule.get("left", ""),
        rule.get("op", "等于"),
        rule.get("right", ""),
    )


def filter_join_rules_to_rows(join_rules):
    return [filter_join_rule_to_row(rule) for rule in (join_rules or []) if isinstance(rule, dict)]


def filter_join_rule_from_row(row):
    values = list(row or [])
    while len(values) < 3:
        values.append("")
    left, op, right = values[:3]
    return {"left": left, "op": op, "right": right}


def filter_join_rules_from_rows(rows):
    return [filter_join_rule_from_row(row) for row in (rows or [])]


def append_filter_join_rule_row(rows, left, op, right):
    result = [tuple(row) for row in (rows or [])]
    rule = filter_join_rule_from_row((left, op, right))
    result.append((rule["left"], rule["op"], rule["right"]))
    return result


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
    return list(fields or [])


def invert_filter_output_fields(fields, selected_fields):
    selected = set(selected_fields or [])
    return [field for field in (fields or []) if field not in selected]


def invert_filter_output_fields_by_indexes(fields, selected_indexes):
    selected = set(selected_indexes or [])
    return [field for index, field in enumerate(fields or []) if index not in selected]


def select_current_table_filter_output_fields(fields):
    return [field for field in (fields or []) if str(field).startswith("当前表.")]
