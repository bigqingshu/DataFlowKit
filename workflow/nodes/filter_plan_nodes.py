# -*- coding: utf-8 -*-
"""Pure planning helpers for the advanced filter workflow node."""

import copy

from core.data_utils import normalize_rows, safe_cell


def make_unique_plan_headers(headers):
    """字段名去重：重复字段自动追加 _2、_3。"""
    result = []
    counts = {}
    for index, header in enumerate(headers, start=1):
        base = str(header).strip() or f"列{index}"
        if base not in counts:
            counts[base] = 1
            result.append(base)
        else:
            counts[base] += 1
            candidate = f"{base}_{counts[base]}"
            while candidate in counts:
                counts[base] += 1
                candidate = f"{base}_{counts[base]}"
            counts[candidate] = 1
            result.append(candidate)
    return result


def plan_filter_field_belongs_to_table(field, table_name):
    return str(field or "").startswith(f"{table_name}.")


def normalize_filter_condition_value_source(cond):
    source = str((cond or {}).get("value_source") or (cond or {}).get("value_mode") or "固定值").strip()
    if source in ["字段值", "指定字段", "表字段", "字段", "按字段值"]:
        return "字段值"
    return "固定值"


def normalize_plan_filter_field_reference(field, headers, extra_tables=None):
    """
    将旧版高级筛选累积出的“当前表.当前表.字段”折叠为当前可用查值键。

    只有折叠结果能精确对应当前 headers 时才转换，避免误伤真实字段名
    本身包含“当前表.”前缀的情况。
    """
    text = str(field or "").strip()
    if not text:
        return ""
    header_names = [str(header) for header in (headers or [])]
    current_lookup_fields = {f"当前表.{header}" for header in header_names}
    if text in current_lookup_fields or text in header_names:
        return text
    for table in extra_tables or []:
        if plan_filter_field_belongs_to_table(text, table):
            return text
    candidate = text
    while candidate.startswith("当前表.当前表."):
        candidate = candidate[len("当前表."):]
        if candidate in current_lookup_fields or candidate in header_names:
            return candidate
    return text


def normalize_plan_filter_config_field_references(config, headers, extra_tables=None):
    """就地升级旧版高级筛选配置中的字段引用。"""
    extra_tables = list(extra_tables or [])
    for cond in config.get("conditions", []) or []:
        if not isinstance(cond, dict):
            continue
        cond["field"] = normalize_plan_filter_field_reference(
            cond.get("field", ""), headers, extra_tables
        )
        if normalize_filter_condition_value_source(cond) == "字段值":
            cond["value"] = normalize_plan_filter_field_reference(
                cond.get("value", ""), headers, extra_tables
            )
    for rule in config.get("join_rules", []) or []:
        if not isinstance(rule, dict):
            continue
        rule["left"] = normalize_plan_filter_field_reference(
            rule.get("left", ""), headers, extra_tables
        )
        rule["right"] = normalize_plan_filter_field_reference(
            rule.get("right", ""), headers, extra_tables
        )
    config["output_fields"] = [
        normalize_plan_filter_field_reference(field, headers, extra_tables)
        for field in (config.get("output_fields", []) or [])
    ]
    return config


def get_plan_filter_output_base_headers(lookup_fields, headers):
    """把内部查值键转换为尚未去重的实际输出字段名。"""
    current_field_names = {
        f"当前表.{header}": str(header)
        for header in (headers or [])
    }
    return [
        current_field_names.get(str(field), str(field))
        for field in (lookup_fields or [])
    ]


def get_plan_filter_output_headers(lookup_fields, headers):
    """
    把高级筛选内部查值键转换为后续节点使用的真实表头。

    当前表字段去掉本轮限定前缀，副表字段保留表名前缀；最终使用稳定编号
    处理重名，保证查值键与输出字段名不再混为一体。
    """
    return make_unique_plan_headers(
        get_plan_filter_output_base_headers(lookup_fields, headers)
    )


def get_plan_filter_output_header_conflicts(lookup_fields, headers):
    """返回会触发自动编号的实际输出字段名。"""
    counts = {}
    for field in get_plan_filter_output_base_headers(lookup_fields, headers):
        name = str(field).strip()
        if name:
            counts[name] = counts.get(name, 0) + 1
    return [name for name, count in counts.items() if count > 1]


def get_plan_filter_field_owner(field, headers, extra_tables):
    field = str(field or "").strip()
    if not field:
        return ""
    if field.startswith("当前表.") or field in set(headers or []):
        return "当前表"
    for table in extra_tables or []:
        if plan_filter_field_belongs_to_table(field, table):
            return table
    return ""


def get_plan_filter_hash_join_availability(headers, extra_tables, join_rules, join_logic):
    availability = {}
    available_sources = {"当前表"}
    if join_logic != "AND":
        for table in extra_tables or []:
            availability[table] = False
            available_sources.add(table)
        return availability

    for table in extra_tables or []:
        table_has_link = False
        for rule in join_rules or []:
            if rule.get("op", "等于") != "等于":
                continue
            left_owner = get_plan_filter_field_owner(rule.get("left", ""), headers, extra_tables)
            right_owner = get_plan_filter_field_owner(rule.get("right", ""), headers, extra_tables)
            if left_owner == table and right_owner in available_sources:
                table_has_link = True
                break
            if right_owner == table and left_owner in available_sources:
                table_has_link = True
                break
        availability[table] = table_has_link
        available_sources.add(table)
    return availability


def get_plan_filter_config_warnings(headers, extra_tables, conditions, join_rules, join_logic):
    extra_tables = list(extra_tables or [])
    if not extra_tables:
        return []

    warnings = []
    if not conditions:
        warnings.append("未设置筛选条件，副表会先按匹配规则读取全部可用行")
    if not join_rules:
        warnings.append("已选择副表但没有多表匹配规则，正式运行可能形成全组合")
        return warnings
    if join_logic != "AND":
        warnings.append("匹配关系为 OR 时无法使用等值索引优化，数据量大时可能较慢")

    availability = get_plan_filter_hash_join_availability(
        headers, extra_tables, join_rules, join_logic
    )
    weak_tables = [table for table in extra_tables if not availability.get(table)]
    if weak_tables:
        warnings.append(
            "以下副表缺少可提前索引的“等于”匹配规则："
            + "、".join(weak_tables)
            + "；建议使用 当前表/已匹配表字段 等于 该副表字段"
        )
    return warnings


def add_plan_filter_required_field(field, headers, extra_tables, current_headers, table_fields):
    field = str(field or "").strip()
    if not field:
        return
    if field.startswith("当前表."):
        if current_headers is None:
            return
        header = field.split(".", 1)[1]
        if header in headers:
            current_headers.add(header)
        return
    if field in headers:
        if current_headers is None:
            return
        current_headers.add(field)
        return
    for table in extra_tables:
        if plan_filter_field_belongs_to_table(field, table) and table_fields.get(table) is not None:
            table_fields[table].add(field)
            return


def collect_plan_filter_required_fields(headers, extra_tables, conditions, join_rules, output_fields, final_fields):
    current_headers = set()
    table_fields = {table: set() for table in extra_tables}
    if not output_fields and extra_tables:
        current_headers = None
        table_fields = {table: None for table in extra_tables}
    else:
        for field in final_fields or []:
            add_plan_filter_required_field(field, headers, extra_tables, current_headers, table_fields)

    for rule in join_rules or []:
        add_plan_filter_required_field(rule.get("left", ""), headers, extra_tables, current_headers, table_fields)
        add_plan_filter_required_field(rule.get("right", ""), headers, extra_tables, current_headers, table_fields)
    for cond in conditions or []:
        add_plan_filter_required_field(cond.get("field", ""), headers, extra_tables, current_headers, table_fields)
        if normalize_filter_condition_value_source(cond) == "字段值":
            add_plan_filter_required_field(cond.get("value", ""), headers, extra_tables, current_headers, table_fields)
    return current_headers, table_fields


def choose_plan_filter_lookup_fields(headers, extra_tables, output_fields, available_fields=None):
    if output_fields:
        return list(output_fields)
    if extra_tables:
        return list(available_fields or [])
    return list(headers)


def build_filter_config_probe_result(output_headers):
    return (
        list(output_headers),
        [],
        f"配置探测：跳过高级筛选多表匹配，仅返回字段结构 {len(output_headers)} 列；正式预览/执行时会按规则计算。",
    )


def build_filter_runtime_plan(headers, config, available_fields=None):
    """构建高级筛选运行计划；副表字段列表由调用方传入，避免纯层触碰外部存储。"""
    runtime_config = copy.deepcopy(config)
    extra_tables = list(runtime_config.get("extra_tables", []))
    normalize_plan_filter_config_field_references(runtime_config, headers, extra_tables)
    conditions = list(runtime_config.get("conditions", []))
    join_rules = list(runtime_config.get("join_rules", []))
    output_fields = list(runtime_config.get("output_fields", []))
    lookup_fields = choose_plan_filter_lookup_fields(headers, extra_tables, output_fields, available_fields=available_fields)
    output_headers = get_plan_filter_output_headers(lookup_fields, headers)
    current_required, table_required = collect_plan_filter_required_fields(
        headers,
        extra_tables,
        conditions,
        join_rules,
        output_fields,
        lookup_fields,
    )
    return {
        "runtime_config": runtime_config,
        "conditions": conditions,
        "join_rules": join_rules,
        "extra_tables": extra_tables,
        "output_fields": output_fields,
        "lookup_fields": lookup_fields,
        "output_headers": output_headers,
        "current_required": current_required,
        "table_required": table_required,
    }


def get_required_columns_for_plan_table(table_name, columns, required_fields):
    if required_fields is None:
        return list(columns)
    wanted = set()
    prefix = f"{table_name}."
    for field in required_fields:
        field = str(field or "")
        if field.startswith(prefix):
            wanted.add(field[len(prefix):])
    return [col for col in columns if col in wanted]


def make_current_table_records(headers, rows, required_headers=None):
    normalized = normalize_rows(rows, len(headers))
    records = []
    if required_headers is None:
        selected_indexes = list(enumerate(headers))
    else:
        required_headers = set(required_headers)
        selected_indexes = [(index, header) for index, header in enumerate(headers) if header in required_headers]
    for row in normalized:
        record = {}
        for index, header in selected_indexes:
            value = safe_cell(row, index)
            # 兼容旧版计划：同时支持“字段名”和“当前表.字段名”。
            record[header] = value
            record[f"当前表.{header}"] = value
        records.append(record)
    return records
