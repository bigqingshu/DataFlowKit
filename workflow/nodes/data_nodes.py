# -*- coding: utf-8 -*-
"""Pure data-shaping workflow nodes."""

import copy
import re
from datetime import datetime

from core.data_utils import make_unique_headers, make_unique_headers_for_append, normalize_rows, safe_cell
from workflow.nodes.data_common import (
    MAX_EXPANDED_ROWS,
    MAX_TARGET_CELLS,
    compare_values,
    ensure_column_count,
    ensure_field_exists,
    ensure_row_count,
    ensure_target_cell_limit,
    field_index,
    get_positive_int,
    get_unique_header,
    last_non_empty_row_index_by_field,
    parse_int,
    parse_row_number,
    parse_separator_text,
    row_is_empty,
    safe_int,
)
from workflow.nodes.numeric_column_nodes import (
    apply_numeric_column_node,
    format_numeric_column_result,
    get_numeric_node_row_indexes,
    numeric_node_fallback_value,
    parse_numeric_value_for_column_op,
)
from workflow.nodes.table_edit_nodes import (
    apply_copy_column_node,
    apply_copy_row_node,
    apply_delete_columns_node,
    apply_delete_rows_node,
    apply_move_columns_node,
    parse_row_spec_to_indexes,
)
from shared.datetime_parse_utils import (
    ambiguous_date_policy,
    ambiguous_delimited_date_warning,
    check_ambiguous_delimited_date,
    complete_year,
    normalize_datetime_text,
    parse_date_auto_common as shared_parse_date_auto_common,
)


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


def resolve_plan_condition_value(record, cond):
    value = (cond or {}).get("value", "")
    if normalize_filter_condition_value_source(cond) != "字段值":
        return value, True
    value_key = str(value or "")
    if value_key not in record:
        return "", False
    return record.get(value_key, ""), True


def eval_plan_condition_record(record, cond):
    field = cond.get("field", "")
    op = cond.get("op", "包含")
    if field not in record:
        return False
    value, value_ok = resolve_plan_condition_value(record, cond)
    if not value_ok and op not in ["为空", "不为空"]:
        return False
    return compare_values(record.get(field, ""), op, value, True)


def eval_plan_join_rule_record(record, rule):
    left_key = rule.get("left", "")
    right_key = rule.get("right", "")
    op = rule.get("op", "等于")
    # 规则引用的字段还没组合进当前中间记录时，暂时不判定，等后续表组合后再生效。
    if left_key not in record or right_key not in record:
        return True
    left = str(record.get(left_key, ""))
    right = str(record.get(right_key, ""))
    if op == "等于":
        return left == right
    if op == "不等于":
        return left != right
    if op == "左包含右":
        return right != "" and right in left
    if op == "右包含左":
        return left != "" and left in right
    if op == "双向包含":
        return left != "" and right != "" and (left in right or right in left)
    return False


def record_passes_plan_conditions(record, conditions, logic):
    if not conditions:
        return True
    checks = [eval_plan_condition_record(record, cond) for cond in conditions]
    return any(checks) if logic == "OR" else all(checks)


def plan_filter_condition_dependencies(cond):
    deps = []
    field = str((cond or {}).get("field", "") or "").strip()
    if field:
        deps.append(field)
    if normalize_filter_condition_value_source(cond) == "字段值":
        value_field = str((cond or {}).get("value", "") or "").strip()
        if value_field:
            deps.append(value_field)
    return deps


def record_survives_available_plan_conditions(record, conditions, logic):
    if not conditions:
        return True
    checks = []
    has_pending = False
    for cond in conditions:
        deps = plan_filter_condition_dependencies(cond)
        if all(dep in record for dep in deps):
            checks.append(eval_plan_condition_record(record, cond))
        else:
            has_pending = True
    if not checks:
        return True
    if logic == "OR":
        return any(checks) or has_pending
    return all(checks)


def record_passes_plan_join_rules(record, join_rules, logic="AND"):
    if not join_rules:
        return True
    checks = [eval_plan_join_rule_record(record, rule) for rule in join_rules]
    return any(checks) if logic == "OR" else all(checks)


def get_plan_filter_hash_join_rules(table_name, join_rules, join_logic, right_records):
    if join_logic != "AND" or not right_records:
        return []
    sample_keys = set()
    for record in right_records:
        sample_keys.update(record.keys())
        if sample_keys:
            break
    hash_rules = []
    for rule in join_rules or []:
        if rule.get("op", "等于") != "等于":
            continue
        left_key = str(rule.get("left", "") or "")
        right_key = str(rule.get("right", "") or "")
        left_is_table = plan_filter_field_belongs_to_table(left_key, table_name)
        right_is_table = plan_filter_field_belongs_to_table(right_key, table_name)
        if left_is_table and not right_is_table and left_key in sample_keys:
            hash_rules.append((right_key, left_key))
        elif right_is_table and not left_is_table and right_key in sample_keys:
            hash_rules.append((left_key, right_key))
    return hash_rules


def build_plan_filter_right_index(right_records, hash_rules):
    index = {}
    missing_key_records = []
    for record in right_records:
        if any(right_key not in record for _, right_key in hash_rules):
            missing_key_records.append(record)
            continue
        key = tuple(str(record.get(right_key, "")) for _, right_key in hash_rules)
        index.setdefault(key, []).append(record)
    return index, missing_key_records


def iter_plan_filter_join_candidates(left_record, right_records, hash_rules, right_index, missing_key_records):
    if not hash_rules:
        return right_records
    if any(left_key not in left_record for left_key, _ in hash_rules):
        return right_records
    key = tuple(str(left_record.get(left_key, "")) for left_key, _ in hash_rules)
    candidates = list(right_index.get(key, []))
    if missing_key_records:
        candidates.extend(missing_key_records)
    return candidates


def apply_filter_node(headers, rows, config, context=None):
    """高级筛选纯计算核心：副表记录由调用方预先加载到 context['table_records']。"""
    conditions = list(config.get("conditions", []))
    join_rules = list(config.get("join_rules", []))
    extra_tables = list(config.get("extra_tables", []))
    logic = config.get("logic", "AND")
    join_logic = config.get("join_logic", "AND")
    output_fields = list(config.get("output_fields", []))
    result_limit = get_positive_int(config.get("result_limit", "5000"), 5000)
    max_intermediate = get_positive_int(config.get("max_intermediate", "200000"), 200000)
    remove_duplicates = bool(config.get("remove_duplicates", False))
    context = context or {}

    if "lookup_fields" in context:
        lookup_fields = list(context.get("lookup_fields") or [])
    elif output_fields:
        lookup_fields = output_fields
    else:
        lookup_fields = list(headers)
    output_headers = list(context.get("output_headers") or get_plan_filter_output_headers(lookup_fields, headers))

    current_required = context.get("current_required", None)
    table_required = context.get("table_required", None)
    if table_required is None and "table_required" not in context:
        current_required, table_required = collect_plan_filter_required_fields(
            headers, extra_tables, conditions, join_rules, output_fields, lookup_fields
        )
    if table_required is None:
        table_required = {table: None for table in extra_tables}

    table_records = context.get("table_records", {})
    records = make_current_table_records(headers, rows, current_required)
    early_filtered = 0
    hash_join_tables = 0
    pruned_table_count = sum(1 for table in extra_tables if table_required.get(table) is not None)
    before_count = len(records)
    records = [
        record for record in records
        if record_survives_available_plan_conditions(record, conditions, logic)
    ]
    early_filtered += before_count - len(records)

    # 多表匹配：以上一步结果作为当前表，依次与已加载副表组合。
    for table in extra_tables:
        right_records = list(table_records.get(table, []))
        before_count = len(right_records)
        right_records = [
            record for record in right_records
            if record_survives_available_plan_conditions(record, conditions, logic)
        ]
        early_filtered += before_count - len(right_records)
        hash_rules = get_plan_filter_hash_join_rules(table, join_rules, join_logic, right_records)
        right_index = {}
        missing_key_records = []
        if hash_rules:
            right_index, missing_key_records = build_plan_filter_right_index(right_records, hash_rules)
            hash_join_tables += 1
        elif not conditions and records and right_records:
            estimated_pairs = len(records) * len(right_records)
            if estimated_pairs > max_intermediate:
                raise RuntimeError(
                    f"高级筛选节点可能形成全组合：当前中间结果 {len(records)} 行 × "
                    f"副表 {table} {len(right_records)} 行 = {estimated_pairs} 组，"
                    f"超过中间组合上限 {max_intermediate}。"
                    "请添加筛选条件，或为该副表添加可索引的“等于”匹配规则"
                    "（当前表/已匹配表字段 等于 该副表字段）。"
                )
        new_records = []
        for left_record in records:
            candidates = iter_plan_filter_join_candidates(
                left_record, right_records, hash_rules, right_index, missing_key_records
            )
            for right_record in candidates:
                merged = {}
                merged.update(left_record)
                merged.update(right_record)
                if (
                    record_passes_plan_join_rules(merged, join_rules, join_logic)
                    and record_survives_available_plan_conditions(merged, conditions, logic)
                ):
                    new_records.append(merged)
                    if len(new_records) > max_intermediate:
                        raise RuntimeError(
                            f"高级筛选节点中间结果超过上限 {max_intermediate} 行。"
                            "请增加匹配规则，或提高中间组合上限。"
                        )
        records = new_records
        if not records:
            break

    result_rows = []
    seen_rows = set()
    duplicate_count = 0
    for record in records:
        if not record_passes_plan_conditions(record, conditions, logic):
            continue
        out_row = [record.get(field, "") for field in lookup_fields]
        if remove_duplicates:
            row_key = tuple("" if value is None else str(value) for value in out_row)
            if row_key in seen_rows:
                duplicate_count += 1
                continue
            seen_rows.add(row_key)
        result_rows.append(out_row)
        if len(result_rows) >= result_limit:
            break

    stat = f"筛选/匹配后 {len(result_rows)} 行"
    if remove_duplicates:
        stat += f"，已去除重复内容 {duplicate_count} 行"
    optimizations = []
    if pruned_table_count:
        optimizations.append(f"字段裁剪 {pruned_table_count} 表")
    if early_filtered:
        optimizations.append(f"提前过滤 {early_filtered} 行")
    if hash_join_tables:
        optimizations.append(f"等值索引匹配 {hash_join_tables} 表")
    if optimizations:
        stat += "；优化：" + "，".join(optimizations)
    return output_headers, result_rows, stat


def get_config_cell_value(headers, rows, config, target_row_idx=None):
    value_source = config.get("value_source", "手动输入值")
    if value_source == "同行来源字段":
        src_idx = field_index(headers, config.get("source_field", ""))
        if target_row_idx is None or target_row_idx < 0 or target_row_idx >= len(rows):
            return ""
        return safe_cell(rows[target_row_idx], src_idx)
    if value_source == "指定单元格值":
        src_idx = field_index(headers, config.get("source_field", ""))
        src_row = parse_row_number(config.get("source_row", "1"), "取值行号") - 1
        if src_row < 0 or src_row >= len(rows):
            return ""
        return safe_cell(rows[src_row], src_idx)
    return str(config.get("manual_value", ""))


def apply_dedupe_node(headers, rows, config, context=None):
    """去重 / 重复数据处理节点。"""
    headers = list(headers)
    normalized = normalize_rows(rows, len(headers))
    if not headers:
        return headers, normalized, "去重：无字段，未处理"

    mode = config.get("dedupe_mode", "指定字段/组合字段去重")
    key_fields = list(config.get("key_fields", []))
    trim = bool(config.get("trim", True))
    ignore_case = bool(config.get("ignore_case", False))
    empty_key_policy = config.get("empty_key_policy", "空键参与去重")
    keep_policy = config.get("keep_policy", "保留第一条")
    output_mode = config.get("output_mode", "输出去重后的数据")
    add_marker = bool(config.get("add_marker_columns", True)) or output_mode == "原表增加重复标记列"

    if mode == "整行去重":
        key_indices = list(range(len(headers)))
        key_names = list(headers)
    else:
        if not key_fields:
            raise ValueError("去重节点需要至少选择一个去重字段。")
        missing = [field for field in key_fields if field not in headers]
        if missing:
            raise ValueError("去重字段不存在：" + ", ".join(missing))
        key_indices = [headers.index(field) for field in key_fields]
        key_names = list(key_fields)

    def normalize_key_value(value):
        text = "" if value is None else str(value)
        if trim:
            text = text.strip()
        if ignore_case:
            text = text.lower()
        return text

    groups = {}
    order = []
    skipped_empty = []
    for row_idx, row in enumerate(normalized):
        _check_cancelled(context, row_idx)
        key = tuple(normalize_key_value(safe_cell(row, index)) for index in key_indices)
        if empty_key_policy == "空键跳过去重" and all(value == "" for value in key):
            skipped_empty.append(row_idx)
            continue
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row_idx)

    keep_indices = set(skipped_empty)
    duplicate_rows = set()
    group_info = {}
    duplicate_group_count = 0

    def non_empty_count(row):
        return sum(1 for cell in row if str(cell).strip() != "")

    for group_index, key in enumerate(order):
        _check_cancelled(context, group_index)
        indexes = groups[key]
        is_duplicate = len(indexes) > 1
        if is_duplicate:
            duplicate_group_count += 1
            group_id = f"DUP_{duplicate_group_count:04d}"
            duplicate_rows.update(indexes)
        else:
            group_id = ""

        if keep_policy == "保留最后一条":
            keep_idx = indexes[-1]
        elif keep_policy == "保留非空字段最多":
            keep_idx = max(indexes, key=lambda index: (non_empty_count(normalized[index]), -index))
        else:
            # “保留第一条”和“不删除，仅标记”都把第一条作为保留标记。
            keep_idx = indexes[0]

        keep_indices.add(keep_idx)
        for pos, row_idx in enumerate(indexes, start=1):
            group_info[row_idx] = {
                "key": key,
                "group_id": group_id,
                "group_index": pos,
                "group_count": len(indexes),
                "is_duplicate": is_duplicate,
                "keep": row_idx == keep_idx,
            }

    for row_idx in skipped_empty:
        group_info[row_idx] = {
            "key": tuple("" for _ in key_indices),
            "group_id": "",
            "group_index": 1,
            "group_count": 1,
            "is_duplicate": False,
            "keep": True,
            "empty_skipped": True,
        }

    if output_mode == "原表增加重复标记列" or keep_policy == "不删除，仅标记":
        selected_indices = list(range(len(normalized)))
        add_marker = True
    elif output_mode == "输出重复项数据":
        selected_indices = [index for index in range(len(normalized)) if index in duplicate_rows]
    elif output_mode == "输出唯一项数据":
        selected_indices = [index for index in range(len(normalized)) if index not in duplicate_rows]
    elif output_mode == "输出重复统计表":
        stat_headers = list(key_names) + ["重复次数", "重复组编号", "是否重复"]
        stat_rows = []
        duplicate_group_no = 0
        for group_index, key in enumerate(order):
            _check_cancelled(context, group_index)
            indexes = groups[key]
            is_duplicate = len(indexes) > 1
            if is_duplicate:
                duplicate_group_no += 1
                gid = f"DUP_{duplicate_group_no:04d}"
            else:
                gid = ""
            stat_rows.append(list(key) + [str(len(indexes)), gid, "是" if is_duplicate else "否"])
        # 空键跳过去重的行单独记为未参与。
        if skipped_empty:
            stat_rows.append(["" for _ in key_names] + [str(len(skipped_empty)), "", "空键跳过"])
        return stat_headers, stat_rows, f"去重统计：共 {len(stat_rows)} 个统计项，重复组 {duplicate_group_count} 个"
    else:
        selected_indices = [index for index in range(len(normalized)) if index in keep_indices]

    out_headers = list(headers)
    if add_marker:
        marker_fields = [
            config.get("duplicate_group_field", "重复组编号") or "重复组编号",
            config.get("duplicate_status_field", "重复状态") or "重复状态",
            config.get("duplicate_index_field", "组内序号") or "组内序号",
            config.get("duplicate_count_field", "重复次数") or "重复次数",
            config.get("keep_flag_field", "是否保留") or "是否保留",
        ]
        marker_fields = make_unique_headers_for_append(out_headers, marker_fields)
        out_headers += marker_fields

    out_rows = []
    for output_index, row_index in enumerate(selected_indices):
        _check_cancelled(context, output_index)
        row = list(normalized[row_index])
        info = group_info.get(row_index, {})
        if add_marker:
            if info.get("empty_skipped"):
                status = "空键跳过"
            elif info.get("is_duplicate"):
                status = "重复"
            else:
                status = "唯一"
            row += [
                info.get("group_id", ""),
                status,
                str(info.get("group_index", "")),
                str(info.get("group_count", "")),
                "是" if info.get("keep") else "否",
            ]
        out_rows.append(row)

    total = len(normalized)
    output_count = len(out_rows)
    duplicate_row_count = len(duplicate_rows)
    if output_mode == "输出去重后的数据":
        action = "输出去重后的数据"
    elif output_mode == "输出重复项数据":
        action = "输出重复项数据"
    elif output_mode == "输出唯一项数据":
        action = "输出唯一项数据"
    else:
        action = "增加重复标记列"
    return out_headers, out_rows, (
        f"去重完成：原 {total} 行，输出 {output_count} 行，"
        f"重复组 {duplicate_group_count} 个，重复行 {duplicate_row_count} 行，模式：{action}"
    )


def match_value_output_column_match(source_value, lookup_value, mode):
    """匹配值输出列名节点的匹配规则。"""
    source_value = "" if source_value is None else str(source_value)
    lookup_value = "" if lookup_value is None else str(lookup_value)
    if mode == "完全相等":
        return source_value == lookup_value
    if mode == "当前值包含匹配值":
        return lookup_value != "" and lookup_value in source_value
    if mode == "匹配值包含当前值":
        return source_value != "" and source_value in lookup_value
    if mode == "忽略大小写完全相等":
        return source_value.lower() == lookup_value.lower()
    if mode == "忽略大小写当前值包含匹配值":
        return lookup_value != "" and lookup_value.lower() in source_value.lower()
    if mode == "忽略大小写匹配值包含当前值":
        return source_value != "" and source_value.lower() in lookup_value.lower()
    if mode == "正则匹配":
        if not lookup_value:
            return False
        try:
            return re.search(lookup_value, source_value) is not None
        except re.error:
            return False
    return False


def apply_match_value_output_field_name_node(headers, rows, config, context=None):
    """匹配值输出列名：用当前表字段值匹配目标记录多个字段，输出命中的字段名。"""
    headers = list(headers)
    rows = normalize_rows(rows, len(headers))
    source_field = str(config.get("source_field", "")).strip()
    lookup_table = str(config.get("lookup_table", "")).strip()
    lookup_fields = [str(field).strip() for field in config.get("lookup_fields", []) if str(field).strip()]
    match_mode = config.get("match_mode", "完全相等")
    if not source_field:
        raise ValueError("请选择当前表匹配字段。")
    if source_field not in headers:
        raise ValueError(f"当前表字段不存在：{source_field}")
    if not lookup_table:
        raise ValueError("请选择匹配表或中转副表。")
    if not lookup_fields:
        raise ValueError("请选择至少一个参与匹配的目标表字段。")

    lookup_columns = list((context or {}).get("lookup_columns", []))
    lookup_records = list((context or {}).get("lookup_records", []))
    missing = [field for field in lookup_fields if field not in lookup_columns]
    if missing:
        raise ValueError("匹配表字段不存在：" + ", ".join(missing))

    output_field = str(config.get("output_field", "匹配字段名")).strip() or "匹配字段名"
    output_match_value = bool(config.get("output_match_value", True))
    match_value_field = str(config.get("match_value_field", "匹配值")).strip() or "匹配值"
    output_match_row = bool(config.get("output_match_row", True))
    match_row_field = str(config.get("match_row_field", "匹配行号")).strip() or "匹配行号"
    output_status = bool(config.get("output_status", True))
    status_field = str(config.get("status_field", "匹配状态")).strip() or "匹配状态"
    multi_policy = config.get("multi_match_policy", "合并所有字段名")
    sep = str(config.get("multi_match_separator", ";"))
    no_match_value = str(config.get("no_match_value", "未匹配"))
    skip_empty_lookup_value = bool(config.get("skip_empty_lookup_value", True))

    source_idx = field_index(headers, source_field)
    out_headers = list(headers)
    out_rows = [list(row) for row in rows]

    def ensure_field(name):
        if not name:
            return None
        if name not in out_headers:
            out_headers.append(name)
            for output_row in out_rows:
                output_row.append("")
        return out_headers.index(name)

    out_idx = ensure_field(output_field)
    match_val_idx = ensure_field(match_value_field) if output_match_value else None
    match_row_idx = ensure_field(match_row_field) if output_match_row else None
    status_idx = ensure_field(status_field) if output_status else None

    success_count = 0
    multi_count = 0
    no_count = 0

    def unique_join(values):
        result = []
        seen = set()
        for value in values:
            text = "" if value is None else str(value)
            if text not in seen:
                result.append(text)
                seen.add(text)
        return sep.join(result)

    for row_index, row in enumerate(out_rows):
        _check_cancelled(context, row_index)
        source_value = safe_cell(row, source_idx)
        matches = []
        if source_value != "":
            for record in lookup_records:
                for field in lookup_fields:
                    lookup_value = str(record.get(field, ""))
                    if skip_empty_lookup_value and lookup_value == "":
                        continue
                    if match_value_output_column_match(source_value, lookup_value, match_mode):
                        matches.append({
                            "field": field,
                            "value": lookup_value,
                            "row_index": record.get("__row_index__", ""),
                        })

        if not matches:
            no_count += 1
            if out_idx is not None:
                row[out_idx] = no_match_value
            if match_val_idx is not None:
                row[match_val_idx] = ""
            if match_row_idx is not None:
                row[match_row_idx] = ""
            if status_idx is not None:
                row[status_idx] = "未匹配"
            continue

        if len(matches) == 1:
            match = matches[0]
            success_count += 1
            if out_idx is not None:
                row[out_idx] = match["field"]
            if match_val_idx is not None:
                row[match_val_idx] = match["value"]
            if match_row_idx is not None:
                row[match_row_idx] = str(match["row_index"])
            if status_idx is not None:
                row[status_idx] = "成功"
        else:
            multi_count += 1
            if multi_policy == "取第一个匹配字段名":
                match = matches[0]
                if out_idx is not None:
                    row[out_idx] = match["field"]
                if match_val_idx is not None:
                    row[match_val_idx] = match["value"]
                if match_row_idx is not None:
                    row[match_row_idx] = str(match["row_index"])
                if status_idx is not None:
                    row[status_idx] = f"多匹配取第一，共{len(matches)}项"
            elif multi_policy == "标记为多匹配":
                if out_idx is not None:
                    row[out_idx] = "多匹配"
                if match_val_idx is not None:
                    row[match_val_idx] = unique_join([match["value"] for match in matches])
                if match_row_idx is not None:
                    row[match_row_idx] = unique_join([match["row_index"] for match in matches])
                if status_idx is not None:
                    row[status_idx] = f"多匹配，共{len(matches)}项"
            else:
                if out_idx is not None:
                    row[out_idx] = unique_join([match["field"] for match in matches])
                if match_val_idx is not None:
                    row[match_val_idx] = unique_join([match["value"] for match in matches])
                if match_row_idx is not None:
                    row[match_row_idx] = unique_join([match["row_index"] for match in matches])
                if status_idx is not None:
                    row[status_idx] = f"多匹配，共{len(matches)}项"

    msg = f"匹配值输出列名完成：成功 {success_count} 行，多匹配 {multi_count} 行，未匹配 {no_count} 行"
    return out_headers, out_rows, msg


def get_row_mapping_end_index(rows, start_idx, config, col_count=None):
    """计算行数据映射节点的结束行下标，返回包含式 end_idx。"""
    total = len(rows)
    if total <= 0:
        return -1
    end_mode = config.get("end_mode", "填充到数据边界")
    if end_mode == "固定行数":
        count = get_positive_int(config.get("count", "1"), 1)
        return min(total - 1, start_idx + count - 1)
    if end_mode == "填充到指定行":
        end_row = parse_row_number(config.get("end_row", "1"), "结束行号") - 1
        return min(total - 1, max(start_idx, end_row))
    return total - 1


def apply_row_data_mapping_node(headers, rows, config):
    """按当前行号同步取值，把每行指定字段展开成多行输出。"""
    headers = list(headers)
    normalized = normalize_rows(rows, len(headers))
    if not normalized:
        return headers, normalized, "当前无数据，未展开"

    value_fields = [field for field in config.get("value_fields", []) if field in headers]
    if not value_fields:
        raise ValueError("请至少选择一个取值字段。")
    keep_fields = [field for field in config.get("keep_fields", []) if field in headers and field not in []]

    start_idx = parse_row_number(config.get("start_row", "1"), "起始行号") - 1
    if start_idx >= len(normalized):
        raise ValueError("起始行号超出当前数据范围。")
    end_idx = get_row_mapping_end_index(normalized, start_idx, config, len(headers))

    value_indexes = [(field, headers.index(field)) for field in value_fields]
    keep_indexes = [(field, headers.index(field)) for field in keep_fields]
    empty_mode = config.get("empty_mode", "跳过空值")
    empty_fixed = str(config.get("empty_fixed", "未填写"))
    trim_value = bool(config.get("trim_value", True))

    out_headers = []
    for field, _ in keep_indexes:
        if field not in out_headers:
            out_headers.append(field)

    if bool(config.get("output_original_row", True)):
        row_field = get_unique_header(config.get("original_row_field", "原始行号"), out_headers)
        out_headers.append(row_field)
    else:
        row_field = None

    if bool(config.get("output_source_field", True)):
        source_field = get_unique_header(config.get("source_field_name", "来源字段"), out_headers)
        out_headers.append(source_field)
    else:
        source_field = None

    value_field = get_unique_header(config.get("output_value_field", "输出内容"), out_headers)
    out_headers.append(value_field)

    if bool(config.get("output_status", True)):
        status_field = get_unique_header(config.get("status_field", "状态"), out_headers)
        out_headers.append(status_field)
    else:
        status_field = None

    out_rows = []
    skipped_empty = 0
    stopped_by_empty_row = False
    for row_idx in range(start_idx, end_idx + 1):
        if row_idx < 0 or row_idx >= len(normalized):
            continue
        row = normalized[row_idx]
        if config.get("end_mode") == "遇到空行停止" and row_is_empty(row, len(headers)):
            stopped_by_empty_row = True
            break

        keep_values = [safe_cell(row, index) for _, index in keep_indexes]
        for field_name, field_idx in value_indexes:
            value = safe_cell(row, field_idx)
            if trim_value:
                value = value.strip()
            status = "成功"
            if value == "":
                if empty_mode == "跳过空值":
                    skipped_empty += 1
                    continue
                if empty_mode == "填写固定值":
                    value = empty_fixed
                    status = "空值已填固定值"
                else:
                    status = "空值"

            out_row = list(keep_values)
            if row_field is not None:
                out_row.append(str(row_idx + 1))
            if source_field is not None:
                out_row.append(field_name)
            out_row.append(value)
            if status_field is not None:
                out_row.append(status)
            out_rows.append(out_row)

    stat = f"按行取值展开 {len(out_rows)} 行"
    if skipped_empty:
        stat += f"，跳过空值 {skipped_empty} 个"
    if stopped_by_empty_row:
        stat += "，遇到空行停止"
    return out_headers, out_rows, stat


def resolve_start_row_index_by_mode(headers, rows, target_field, config):
    mode = config.get("start_row_mode", "手动指定起始行")
    if mode == "目标列最后数据行之后":
        try:
            last_idx = last_non_empty_row_index_by_field(headers, rows, target_field)
        except Exception:
            last_idx = -1
        return max(0, last_idx + 1)
    if mode == "参考列最后数据行之后":
        last_idx = last_non_empty_row_index_by_field(headers, rows, config.get("reference_field", ""))
        return max(0, last_idx + 1)
    if mode == "整体表格最后行之后":
        return max(0, len(rows))
    return parse_row_number(config.get("start_row", "1"), "起始行号") - 1


def get_source_column_values_by_config(headers, rows, config):
    src_idx = field_index(headers, config.get("source_field", ""))
    normalized = normalize_rows(rows, len(headers))
    mode = config.get("source_range_mode", "来源列数据边界")
    start_row = parse_row_number(config.get("source_start_row", "1"), "来源起始行") - 1
    if mode == "整体表格数据边界":
        end_row = len(normalized) - 1
    elif mode == "手动指定范围":
        end_row = parse_row_number(config.get("source_end_row", "1"), "来源结束行") - 1
    else:
        end_row = last_non_empty_row_index_by_field(headers, normalized, config.get("source_field", ""))
    if end_row < 0 or start_row > end_row:
        return []
    start_row = max(0, start_row)
    end_row = min(end_row, len(normalized) - 1)
    return [safe_cell(normalized[r], src_idx) for r in range(start_row, end_row + 1)]


def get_source_area_values_by_config(headers, rows, config):
    normalized = normalize_rows(rows, len(headers))
    if not normalized:
        return []

    start_col = field_index(headers, config.get("source_field", ""))
    end_field = config.get("source_end_field", config.get("source_field", ""))
    end_col = field_index(headers, end_field)
    c1, c2 = sorted([start_col, end_col])

    mode = config.get("source_range_mode", "来源列数据边界")
    start_row = parse_row_number(config.get("source_start_row", "1"), "来源起始行") - 1
    if mode == "整体表格数据边界":
        end_row = len(normalized) - 1
    elif mode == "手动指定范围":
        end_row = parse_row_number(config.get("source_end_row", "1"), "来源结束行") - 1
    else:
        end_row = last_non_empty_row_index_by_field(headers, normalized, config.get("source_field", ""))

    if end_row < 0 or start_row > end_row:
        return []
    start_row = max(0, start_row)
    end_row = min(end_row, len(normalized) - 1)
    return [
        [safe_cell(normalized[r], c) for c in range(c1, c2 + 1)]
        for r in range(start_row, end_row + 1)
    ]


def get_source_row_multi_field_values_by_config(headers, rows, config):
    normalized = normalize_rows(rows, len(headers))
    src_row = parse_row_number(config.get("source_row", "1"), "取值行号") - 1
    if src_row < 0 or src_row >= len(normalized):
        return []
    start_idx = field_index(headers, config.get("source_field", ""))
    end_field = config.get("source_end_field", config.get("source_field", ""))
    end_idx = field_index(headers, end_field)
    c1, c2 = sorted([start_idx, end_idx])
    return [safe_cell(normalized[src_row], c) for c in range(c1, c2 + 1)]


def get_cycle_source_values_by_config(headers, rows, config, multi_field=False):
    if multi_field:
        source_area = get_source_area_values_by_config(headers, rows, config)
        raw_values = []
        for source_row in source_area:
            raw_values.extend(source_row)
    else:
        raw_values = get_source_column_values_by_config(headers, rows, config)

    empty_mode = config.get("source_empty_mode", "跳过空值")
    placeholder = str(config.get("source_empty_placeholder", ""))
    values = []
    for value in raw_values:
        text = "" if value is None else str(value)
        if text == "":
            if empty_mode == "跳过空值":
                continue
            if empty_mode == "替换为空值占位符":
                text = placeholder
        values.append(text)
    return values


def resolve_sequence_count_by_source(headers, rows, config):
    mode = config.get("count_source_mode", "使用结束条件")
    if mode == "整体表格数据行数":
        return max(0, len(rows))
    if mode == "指定参考列数据数量":
        last_idx = last_non_empty_row_index_by_field(headers, rows, config.get("reference_field", ""))
        return max(0, last_idx + 1)
    if mode == "来源列数据数量":
        return len(get_source_column_values_by_config(headers, rows, config))
    return None


def resolve_area_end_row_index(headers, rows, config):
    mode = config.get("end_row_mode", "手动指定结束行")
    if mode == "整体表格数据边界":
        return max(0, len(rows) - 1)
    if mode == "指定参考列数据边界":
        return last_non_empty_row_index_by_field(headers, rows, config.get("reference_field", ""))
    return parse_row_number(config.get("end_row", "1"), "结束行号") - 1


def get_fill_targets(
    headers,
    rows,
    target_field,
    start_row_value,
    direction,
    end_mode,
    count_value,
    end_row_value,
    end_field_value,
    reference_field_value="",
    allow_expand_rows=True,
    allow_expand_cols=False,
    max_expanded_rows=MAX_EXPANDED_ROWS,
    max_target_cells=MAX_TARGET_CELLS,
):
    headers, rows, target_col = ensure_field_exists(headers, rows, target_field)
    start_row = parse_row_number(start_row_value, "起始行号") - 1
    rows = ensure_row_count(rows, start_row + 1, len(headers), max_expanded_rows=max_expanded_rows)
    direction = direction or "向下"
    end_mode = end_mode or "固定数量"
    count = get_positive_int(count_value, 1)
    targets = []

    def ensure_cols(col_index):
        nonlocal headers, rows
        while col_index >= len(headers):
            headers.append(get_unique_header(f"填充列{len(headers)+1}", headers))
            for row in rows:
                row.append("")

    if direction in ["向下", "向上"]:
        if end_mode == "固定数量":
            end_row = start_row + count - 1 if direction == "向下" else start_row - count + 1
        elif end_mode == "填充到指定行":
            end_row = parse_row_number(end_row_value, "结束行号") - 1
        elif end_mode == "填充到参考列数据边界":
            ref_last = last_non_empty_row_index_by_field(headers, rows, reference_field_value)
            end_row = ref_last if direction == "向下" else 0
        elif end_mode in ["填充到数据边界", "填充到指定列"]:
            end_row = len(rows) - 1 if direction == "向下" else 0
        elif end_mode in ["遇到已有数据停止", "填充到空行前"]:
            end_row = len(rows) - 1 if direction == "向下" else 0
        else:
            end_row = len(rows) - 1 if direction == "向下" else 0
        target_count = abs(end_row - start_row) + 1
        ensure_target_cell_limit(1, target_count, max_target_cells=max_target_cells)
        if allow_expand_rows and direction == "向下" and end_row >= len(rows):
            rows = ensure_row_count(rows, end_row + 1, len(headers), max_expanded_rows=max_expanded_rows)
        step = 1 if direction == "向下" else -1
        r = start_row
        while 0 <= r < len(rows) and ((step > 0 and r <= end_row) or (step < 0 and r >= end_row)):
            if end_mode == "填充到空行前" and row_is_empty(rows[r], len(headers)):
                break
            targets.append((r, target_col))
            r += step
    else:
        if end_mode == "固定数量":
            end_col = target_col + count - 1 if direction == "向右" else target_col - count + 1
        elif end_mode == "填充到指定列":
            if end_field_value not in headers:
                if allow_expand_cols and direction == "向右":
                    headers, rows, end_col = ensure_field_exists(headers, rows, end_field_value)
                else:
                    raise ValueError(f"结束字段不存在：{end_field_value}")
            else:
                end_col = headers.index(end_field_value)
        else:
            end_col = len(headers) - 1 if direction == "向右" else 0
        target_count = abs(end_col - target_col) + 1
        ensure_target_cell_limit(1, target_count, max_target_cells=max_target_cells)
        if allow_expand_cols and direction == "向右" and end_col >= len(headers):
            ensure_cols(end_col)
        step = 1 if direction == "向右" else -1
        c = target_col
        while 0 <= c < len(headers) and ((step > 0 and c <= end_col) or (step < 0 and c >= end_col)):
            targets.append((start_row, c))
            c += step
    return headers, rows, targets


def should_write_cell(current_value, overwrite_rule):
    current = "" if current_value is None else str(current_value)
    if overwrite_rule == "覆盖所有目标单元格":
        return True, False
    if overwrite_rule == "只填充空单元格":
        return current == "", False
    if overwrite_rule == "遇到已有数据停止":
        return current == "", current != ""
    if overwrite_rule == "不覆盖已有数据，只跳过":
        return current == "", False
    return True, False


def format_sequence_value(value, config):
    zero_pad = get_positive_int(config.get("zero_pad", "0"), 0) if str(config.get("zero_pad", "0")).strip() != "0" else 0
    if abs(value - int(value)) < 1e-12:
        text = str(int(value))
        if zero_pad > 0:
            text = text.zfill(zero_pad)
    else:
        text = str(value).rstrip("0").rstrip(".") if "." in str(value) else str(value)
    return f"{config.get('prefix', '')}{text}{config.get('suffix', '')}"


def _check_cancelled(context, index):
    callback = (context or {}).get("check_cancelled")
    if callable(callback):
        callback(index)


def replace_row_index_for_policy(policy, current_index, pair_index, fixed_index):
    policy = str(policy or "当前行").strip()
    if policy == "第一行":
        return 0
    if policy == "固定行号":
        return fixed_index - 1
    if policy in ("按匹配行号", "按命中序号"):
        return pair_index
    return current_index


def replace_source_value(rows, source, field_idx, fixed_value, policy, current_index, pair_index, fixed_index):
    if source != "列字段":
        return fixed_value, True
    row_index = replace_row_index_for_policy(policy, current_index, pair_index, fixed_index)
    if row_index < 0 or row_index >= len(rows):
        return "", False
    return safe_cell(rows[row_index], field_idx), True


def replace_pair_count_for_row(new_rows, match_source, match_row_policy, replace_source, replace_row_policy):
    counts = []
    if match_source == "列字段" and match_row_policy in ("按匹配行号", "按命中序号"):
        counts.append(len(new_rows))
    if replace_source == "列字段" and replace_row_policy in ("按匹配行号", "按命中序号"):
        counts.append(len(new_rows))
    return max(counts) if counts else 1


def apply_replace_node(headers, rows, config, context=None):
    idx = field_index(headers, config.get("target_field", ""))
    match_mode = config.get("match_mode", "包含")
    replace_mode = config.get("replace_mode", "局部替换匹配字符串")
    case_sensitive = bool(config.get("case_sensitive", True))
    skip_empty_match_value = bool(config.get("skip_empty_match_value", True))
    legacy_value_source = config.get("value_source", "手动输入")
    match_source = config.get("match_value_source") or legacy_value_source or "手动输入"
    replace_source = config.get("replace_value_source") or legacy_value_source or "手动输入"
    match_source = "列字段" if match_source in ("列字段", "字段", "当前表字段") else "手动输入"
    replace_source = "列字段" if replace_source in ("列字段", "字段", "当前表字段") else "手动输入"
    match_row_policy = config.get("match_row_policy") or ("当前行" if legacy_value_source == "列字段" else "当前行")
    replace_row_policy = config.get("replace_row_policy") or ("当前行" if legacy_value_source == "列字段" else "当前行")
    match_row_index = max(1, safe_int(config.get("match_row_index", 1), 1))
    replace_row_index = max(1, safe_int(config.get("replace_row_index", 1), 1))
    replace_count = max(0, safe_int(config.get("replace_count", 0), 0))

    match_field_idx = field_index(headers, config.get("match_value_field", "")) if match_source == "列字段" else None
    replace_field_idx = field_index(headers, config.get("replace_value_field", "")) if replace_source == "列字段" else None
    static_match_value = str(config.get("match_value", ""))
    static_replace_value = str(config.get("replace_value", ""))
    if match_mode == "正则匹配" and match_source != "列字段":
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            re.compile(static_match_value, flags=flags)
        except re.error as exc:
            raise ValueError(f"批量替换正则错误：{exc}") from exc

    new_rows = normalize_rows(rows, len(headers))
    changed = 0
    skipped_empty = 0
    skipped_invalid_row = 0

    def replace_text(old, match_value, replace_value):
        if replace_mode == "整格替换为新值":
            return replace_value
        if match_mode == "正则匹配":
            flags = 0 if case_sensitive else re.IGNORECASE
            return re.sub(match_value, replace_value, old, count=replace_count, flags=flags)
        if match_value == "":
            return old
        if case_sensitive:
            return old.replace(match_value, replace_value, replace_count if replace_count else -1)
        return re.sub(re.escape(match_value), replace_value, old, count=replace_count, flags=re.IGNORECASE)

    for row_index, row in enumerate(new_rows):
        _check_cancelled(context, row_index)
        old = safe_cell(row, idx)
        new_value = old
        row_changed = False
        for pair_index in range(
            replace_pair_count_for_row(new_rows, match_source, match_row_policy, replace_source, replace_row_policy)
        ):
            match_value, match_row_ok = replace_source_value(
                new_rows, match_source, match_field_idx, static_match_value, match_row_policy, row_index, pair_index, match_row_index
            )
            replace_value, replace_row_ok = replace_source_value(
                new_rows, replace_source, replace_field_idx, static_replace_value, replace_row_policy, row_index, pair_index, replace_row_index
            )
            if not match_row_ok or not replace_row_ok:
                skipped_invalid_row += 1
                continue
            if skip_empty_match_value and match_value == "" and match_mode not in ("为空", "不为空"):
                skipped_empty += 1
                continue
            try:
                matched = compare_values(new_value, match_mode, match_value, case_sensitive)
            except re.error as exc:
                raise ValueError(
                    f"批量替换正则错误（第 {row_index + 1} 行，匹配值 {match_value!r}）：{exc}"
                ) from exc
            if not matched:
                continue
            try:
                updated = replace_text(new_value, match_value, replace_value)
            except re.error as exc:
                raise ValueError(
                    f"批量替换正则错误（第 {row_index + 1} 行，匹配值 {match_value!r}）：{exc}"
                ) from exc
            if updated != new_value:
                new_value = updated
                row_changed = True
        if new_value != old:
            row[idx] = new_value
        if row_changed:
            changed += 1

    extras = []
    if (match_source == "列字段" or replace_source == "列字段") and skipped_empty:
        extras.append(f"跳过空匹配值 {skipped_empty} 次")
    if skipped_invalid_row:
        extras.append(f"跳过无效取行 {skipped_invalid_row} 次")
    extra = "，" + "，".join(extras) if extras else ""
    return list(headers), new_rows, f"修改 {changed} 处{extra}"


def apply_merge_node(headers, rows, config, context=None):
    fields = list(config.get("fields", []))
    if not fields:
        raise ValueError("合并字段不能为空。")
    indexes = [field_index(headers, field) for field in fields]
    seps = [parse_separator_text(sep) for sep in list(config.get("separators", []))]
    if len(seps) < max(len(fields) - 1, 0):
        seps += [""] * (len(fields) - 1 - len(seps))

    output_field = get_unique_header(config.get("output_field", "合并结果"), headers)
    new_headers = list(headers) + [output_field]
    new_rows = normalize_rows(rows, len(headers))
    skip_empty = bool(config.get("skip_empty", True))
    trim_value = bool(config.get("trim_value", True))
    placeholder = str(config.get("empty_placeholder", ""))

    for row_index, row in enumerate(new_rows):
        _check_cancelled(context, row_index)
        pieces = []
        active_indexes = []
        for index, field_idx in enumerate(indexes):
            value = safe_cell(row, field_idx)
            if trim_value:
                value = value.strip()
            if value == "" and placeholder:
                value = placeholder
            if skip_empty and value == "":
                continue
            active_indexes.append(index)
            pieces.append(value)

        if not pieces:
            merged = ""
        elif skip_empty:
            merged = pieces[0]
            for piece_index in range(1, len(pieces)):
                original_gap_index = active_indexes[piece_index - 1]
                sep = seps[original_gap_index] if original_gap_index < len(seps) else ""
                merged += sep + pieces[piece_index]
        else:
            merged = pieces[0]
            for piece_index in range(1, len(pieces)):
                sep = seps[piece_index - 1] if piece_index - 1 < len(seps) else ""
                merged += sep + pieces[piece_index]
        row.append(merged)

    return new_headers, new_rows, f"新增字段 {output_field}"


def apply_rename_columns_node(headers, rows, config):
    headers = list(headers)
    new_headers = list(headers)
    mode = config.get("mode", "手动映射改名")
    trim_names = bool(config.get("trim_names", True))
    duplicate_policy = config.get("duplicate_policy", "自动追加编号")
    missing_policy = config.get("missing_policy", "跳过并记录警告")
    warnings = []
    changed = 0

    def clean_name(name):
        value = "" if name is None else str(name)
        return value.strip() if trim_names else value

    def field_scope_indexes():
        if config.get("scope", "全部字段") == "选中字段":
            selected = set(config.get("scope_fields", []))
            return [index for index, header in enumerate(headers) if header in selected]
        return list(range(len(headers)))

    if mode == "手动映射改名":
        old_to_new = {}
        for item in config.get("mappings", []):
            old = str(item.get("old", "")).strip()
            new = clean_name(item.get("new", ""))
            if old:
                old_to_new[old] = new
        for old, new in old_to_new.items():
            if old not in headers:
                message = f"字段不存在：{old}"
                if missing_policy == "报错并停止":
                    raise ValueError(message)
                warnings.append(message)
                continue
            idx = headers.index(old)
            if new:
                if new_headers[idx] != new:
                    changed += 1
                new_headers[idx] = new
    elif mode == "批量添加前缀":
        prefix = str(config.get("prefix", ""))
        for idx in field_scope_indexes():
            new_name = clean_name(prefix + str(headers[idx]))
            if new_headers[idx] != new_name:
                changed += 1
            new_headers[idx] = new_name
    elif mode == "批量添加后缀":
        suffix = str(config.get("suffix", ""))
        for idx in field_scope_indexes():
            new_name = clean_name(str(headers[idx]) + suffix)
            if new_headers[idx] != new_name:
                changed += 1
            new_headers[idx] = new_name
    elif mode == "批量替换字段名字符":
        match = str(config.get("replace_match", ""))
        repl = str(config.get("replace_value", ""))
        if not match:
            return list(headers), [list(row) for row in rows], "字段名替换匹配值为空，未修改"
        for idx in field_scope_indexes():
            new_name = clean_name(str(headers[idx]).replace(match, repl))
            if new_headers[idx] != new_name:
                changed += 1
            new_headers[idx] = new_name
    else:
        raise ValueError(f"未知改名模式：{mode}")

    for index, name in enumerate(new_headers):
        if str(name).strip() == "":
            new_headers[index] = f"列{index + 1}"
            warnings.append(f"第{index + 1}列字段名为空，已自动改为 列{index + 1}")

    if duplicate_policy == "自动追加编号":
        new_headers = make_unique_headers(new_headers)
    else:
        seen = set()
        duplicates = []
        for header in new_headers:
            if header in seen:
                duplicates.append(header)
            seen.add(header)
        if duplicates:
            raise ValueError("字段名重复：" + ", ".join(dict.fromkeys(duplicates)))

    message = f"已更改 {changed} 个字段名"
    if warnings:
        message += f"，警告 {len(warnings)} 项"
    return new_headers, [list(row) for row in rows], message


def apply_fill_value_node(headers, rows, config, context=None):
    headers = list(headers)
    rows = normalize_rows(rows, len(headers))
    value_source = config.get("value_source", "手动输入值")
    target_field = config.get("target_field", "")
    max_expanded_rows = (context or {}).get("max_expanded_rows", MAX_EXPANDED_ROWS)
    max_target_cells = (context or {}).get("max_target_cells", MAX_TARGET_CELLS)

    if value_source == "循环源列填充":
        effective_start_row = resolve_start_row_index_by_mode(headers, rows, target_field, config) + 1
        headers, rows, targets = get_fill_targets(
            headers,
            rows,
            target_field,
            str(effective_start_row),
            config.get("direction", "向下"),
            config.get("end_mode", "填充到数据边界"),
            config.get("count", "1"),
            config.get("end_row", "1"),
            config.get("end_field", ""),
            config.get("reference_field", ""),
            allow_expand_rows=True,
            allow_expand_cols=True,
            max_expanded_rows=max_expanded_rows,
            max_target_cells=max_target_cells,
        )
        cycle_values = get_cycle_source_values_by_config(headers, rows, config)
        if not cycle_values:
            return headers, rows, "循环源列无可用数据，未执行填充"
        overwrite_rule = config.get("overwrite_rule", "只填充空单元格")
        changed = skipped = write_index = 0
        for target_index, (r, c) in enumerate(targets):
            _check_cancelled(context, target_index)
            rows = ensure_row_count(rows, r + 1, len(headers), max_expanded_rows=max_expanded_rows)
            can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
            if stop:
                break
            if can_write:
                rows[r][c] = cycle_values[write_index % len(cycle_values)]
                changed += 1
                write_index += 1
            else:
                skipped += 1
        return headers, rows, f"循环源列填充 {changed} 个单元格，跳过 {skipped} 个，循环周期 {len(cycle_values)}"

    if value_source == "来源列完整结构":
        headers, rows, target_col = ensure_field_exists(headers, rows, target_field)
        start_row = resolve_start_row_index_by_mode(headers, rows, target_field, config)
        values = get_source_column_values_by_config(headers, rows, config)
        if not values:
            return headers, rows, "来源列无可填充数据，未执行填充"
        rows = ensure_row_count(rows, start_row + len(values), len(headers), max_expanded_rows=max_expanded_rows)
        overwrite_rule = config.get("overwrite_rule", "只填充空单元格")
        changed = skipped = 0
        for offset, value in enumerate(values):
            _check_cancelled(context, offset)
            r = start_row + offset
            can_write, stop = should_write_cell(safe_cell(rows[r], target_col), overwrite_rule)
            if stop:
                break
            if can_write:
                rows[r][target_col] = value
                changed += 1
            else:
                skipped += 1
        return headers, rows, f"来源列完整结构填充 {changed} 个单元格，跳过 {skipped} 个"

    effective_start_row = resolve_start_row_index_by_mode(headers, rows, target_field, config) + 1
    headers, rows, targets = get_fill_targets(
        headers,
        rows,
        target_field,
        str(effective_start_row),
        config.get("direction", "向下"),
        config.get("end_mode", "填充到数据边界"),
        config.get("count", "1"),
        config.get("end_row", "1"),
        config.get("end_field", ""),
        config.get("reference_field", ""),
        allow_expand_rows=True,
        allow_expand_cols=True,
        max_expanded_rows=max_expanded_rows,
        max_target_cells=max_target_cells,
    )
    changed = skipped = 0
    overwrite_rule = config.get("overwrite_rule", "只填充空单元格")
    for target_index, (r, c) in enumerate(targets):
        _check_cancelled(context, target_index)
        rows = ensure_row_count(rows, r + 1, len(headers), max_expanded_rows=max_expanded_rows)
        can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
        if stop:
            break
        if can_write:
            rows[r][c] = get_config_cell_value(headers, rows, config, target_row_idx=r)
            changed += 1
        else:
            skipped += 1
    return headers, rows, f"填充 {changed} 个单元格，跳过 {skipped} 个"


def apply_sequence_fill_node(headers, rows, config, context=None):
    headers = list(headers)
    rows = normalize_rows(rows, len(headers))
    max_expanded_rows = (context or {}).get("max_expanded_rows", MAX_EXPANDED_ROWS)
    max_target_cells = (context or {}).get("max_target_cells", MAX_TARGET_CELLS)
    try:
        start_value = float(str(config.get("start_value", "1")).strip())
        step = float(str(config.get("step", "1")).strip())
    except Exception:
        raise ValueError("起始值和步长必须是数字。")

    target_field = config.get("target_field", "")
    effective_start_row = resolve_start_row_index_by_mode(headers, rows, target_field, config) + 1
    count_override = resolve_sequence_count_by_source(headers, rows, config)
    end_mode = config.get("end_mode", "填充到数据边界")
    count_value = config.get("count", "1")
    if count_override is not None:
        end_mode = "固定数量"
        count_value = str(count_override)

    headers, rows, targets = get_fill_targets(
        headers,
        rows,
        target_field,
        str(effective_start_row),
        config.get("direction", "向下"),
        end_mode,
        count_value,
        config.get("end_row", "1"),
        config.get("end_field", ""),
        config.get("reference_field", ""),
        allow_expand_rows=True,
        allow_expand_cols=True,
        max_expanded_rows=max_expanded_rows,
        max_target_cells=max_target_cells,
    )
    changed = skipped = seq_index = 0
    overwrite_rule = config.get("overwrite_rule", "覆盖所有目标单元格")
    for target_index, (r, c) in enumerate(targets):
        _check_cancelled(context, target_index)
        rows = ensure_row_count(rows, r + 1, len(headers), max_expanded_rows=max_expanded_rows)
        can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
        if stop:
            break
        if can_write:
            rows[r][c] = format_sequence_value(start_value + step * seq_index, config)
            changed += 1
            seq_index += 1
        else:
            skipped += 1
    return headers, rows, f"序列填充 {changed} 个单元格，跳过 {skipped} 个"


def apply_area_fill_node(headers, rows, config, context=None):
    headers = list(headers)
    rows = normalize_rows(rows, len(headers))
    max_expanded_rows = (context or {}).get("max_expanded_rows", MAX_EXPANDED_ROWS)
    max_target_cells = (context or {}).get("max_target_cells", MAX_TARGET_CELLS)
    if config.get("start_field", "") not in headers:
        headers, rows, start_col = ensure_field_exists(headers, rows, config.get("start_field", ""))
    else:
        start_col = headers.index(config.get("start_field", ""))
    if config.get("end_field", "") not in headers:
        headers, rows, end_col = ensure_field_exists(headers, rows, config.get("end_field", ""))
    else:
        end_col = headers.index(config.get("end_field", ""))

    start_row = resolve_start_row_index_by_mode(headers, rows, config.get("start_field", ""), config)
    value_source = config.get("value_source", "手动输入值")
    c1, c2 = sorted([start_col, end_col])
    overwrite_rule = config.get("overwrite_rule", "只填充空单元格")
    changed = skipped = 0

    if value_source == "循环源列填充":
        cycle_values = get_cycle_source_values_by_config(headers, rows, config, multi_field=True)
        if not cycle_values:
            return headers, rows, "循环源列无可用数据，未执行区域填充"
        end_row = resolve_area_end_row_index(headers, rows, config)
        if end_row < 0:
            return headers, rows, "参考列无数据，未执行区域填充"
        r1, r2 = sorted([start_row, end_row])
        ensure_target_cell_limit(r2 - r1 + 1, c2 - c1 + 1, max_target_cells=max_target_cells)
        rows = ensure_row_count(rows, r2 + 1, len(headers), max_expanded_rows=max_expanded_rows)
        stop_all = False
        write_index = 0
        for r in range(r1, r2 + 1):
            _check_cancelled(context, r - r1)
            if stop_all:
                break
            for c in range(c1, c2 + 1):
                can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
                if stop:
                    stop_all = True
                    break
                if can_write:
                    rows[r][c] = cycle_values[write_index % len(cycle_values)]
                    changed += 1
                    write_index += 1
                else:
                    skipped += 1
        return headers, rows, f"循环源列区域填充 {changed} 个单元格，跳过 {skipped} 个，循环周期 {len(cycle_values)}（多源字段）"

    if value_source == "来源区域完整复制":
        source_area = get_source_area_values_by_config(headers, rows, config)
        if not source_area:
            return headers, rows, "来源区域为空或越界，未执行区域完整复制"
        source_height = len(source_area)
        source_width = max((len(row) for row in source_area), default=0)
        if source_height <= 0 or source_width <= 0:
            return headers, rows, "来源区域为空，未执行区域完整复制"
        ensure_target_cell_limit(source_height, source_width, max_target_cells=max_target_cells)

        headers, rows = ensure_column_count(headers, rows, start_col + source_width, "区域复制列")
        rows = ensure_row_count(rows, start_row + source_height, len(headers), max_expanded_rows=max_expanded_rows)
        stop_all = False
        for r_offset, source_row in enumerate(source_area):
            _check_cancelled(context, r_offset)
            if stop_all:
                break
            target_r = start_row + r_offset
            for c_offset, value in enumerate(source_row):
                target_c = start_col + c_offset
                can_write, stop = should_write_cell(safe_cell(rows[target_r], target_c), overwrite_rule)
                if stop:
                    stop_all = True
                    break
                if can_write:
                    rows[target_r][target_c] = value
                    changed += 1
                else:
                    skipped += 1
        return headers, rows, f"来源区域完整复制 {changed} 个单元格，跳过 {skipped} 个"

    if value_source == "来源列完整结构":
        values = get_source_column_values_by_config(headers, rows, config)
        if not values:
            return headers, rows, "来源列无可填充数据，未执行区域填充"
        ensure_target_cell_limit(len(values), c2 - c1 + 1, max_target_cells=max_target_cells)
        rows = ensure_row_count(rows, start_row + len(values), len(headers), max_expanded_rows=max_expanded_rows)
        stop_all = False
        for offset, value in enumerate(values):
            _check_cancelled(context, offset)
            if stop_all:
                break
            r = start_row + offset
            for c in range(c1, c2 + 1):
                can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
                if stop:
                    stop_all = True
                    break
                if can_write:
                    rows[r][c] = value
                    changed += 1
                else:
                    skipped += 1
        return headers, rows, f"来源列完整结构区域填充 {changed} 个单元格，跳过 {skipped} 个"

    if value_source == "指定行多字段取值":
        values = get_source_row_multi_field_values_by_config(headers, rows, config)
        if not values:
            return headers, rows, "指定行多字段取值为空或越界，未执行区域填充"
        direction = config.get("multi_field_fill_direction", "横向填充")
        if direction == "纵向填充":
            ensure_target_cell_limit(len(values), c2 - c1 + 1, max_target_cells=max_target_cells)
            rows = ensure_row_count(rows, start_row + len(values), len(headers), max_expanded_rows=max_expanded_rows)
            stop_all = False
            for offset, value in enumerate(values):
                _check_cancelled(context, offset)
                if stop_all:
                    break
                r = start_row + offset
                for c in range(c1, c2 + 1):
                    can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
                    if stop:
                        stop_all = True
                        break
                    if can_write:
                        rows[r][c] = value
                        changed += 1
                    else:
                        skipped += 1
        else:
            end_row = resolve_area_end_row_index(headers, rows, config)
            if end_row < 0:
                return headers, rows, "参考列无数据，未执行区域填充"
            r1, r2 = sorted([start_row, end_row])
            ensure_target_cell_limit(r2 - r1 + 1, min(c2 - c1 + 1, len(values)), max_target_cells=max_target_cells)
            rows = ensure_row_count(rows, r2 + 1, len(headers), max_expanded_rows=max_expanded_rows)
            target_cols = list(range(c1, c2 + 1))
            stop_all = False
            for r in range(r1, r2 + 1):
                _check_cancelled(context, r - r1)
                if stop_all:
                    break
                for offset, c in enumerate(target_cols):
                    if offset >= len(values):
                        break
                    value = values[offset]
                    can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
                    if stop:
                        stop_all = True
                        break
                    if can_write:
                        rows[r][c] = value
                        changed += 1
                    else:
                        skipped += 1
        return headers, rows, f"指定行多字段取值区域填充 {changed} 个单元格，跳过 {skipped} 个"

    end_row = resolve_area_end_row_index(headers, rows, config)
    if end_row < 0:
        return headers, rows, "参考列无数据，未执行区域填充"
    r1, r2 = sorted([start_row, end_row])
    ensure_target_cell_limit(r2 - r1 + 1, c2 - c1 + 1, max_target_cells=max_target_cells)
    rows = ensure_row_count(rows, r2 + 1, len(headers), max_expanded_rows=max_expanded_rows)
    stop_all = False
    for r in range(r1, r2 + 1):
        _check_cancelled(context, r - r1)
        if stop_all:
            break
        for c in range(c1, c2 + 1):
            can_write, stop = should_write_cell(safe_cell(rows[r], c), overwrite_rule)
            if stop:
                stop_all = True
                break
            if can_write:
                rows[r][c] = get_config_cell_value(headers, rows, config, target_row_idx=r)
                changed += 1
            else:
                skipped += 1
    return headers, rows, f"区域填充 {changed} 个单元格，跳过 {skipped} 个"


def render_current_datetime_template(dt, config):
    mode = config.get("format_mode", "占位符模板")
    if mode == "Python strftime":
        fmt = str(config.get("strftime_template", "%Y-%m-%d %H:%M:%S") or "%Y-%m-%d %H:%M:%S")
        try:
            return dt.strftime(fmt)
        except Exception as exc:
            raise ValueError(f"strftime格式错误：{exc}") from exc

    values = {
        "YYYY": f"{dt.year:04d}",
        "YY": f"{dt.year % 100:02d}",
        "MM": f"{dt.month:02d}",
        "M": str(dt.month),
        "DD": f"{dt.day:02d}",
        "D": str(dt.day),
        "HH": f"{dt.hour:02d}",
        "H": str(dt.hour),
        "mm": f"{dt.minute:02d}",
        "m": str(dt.minute),
        "ss": f"{dt.second:02d}",
        "s": str(dt.second),
        "fff": f"{dt.microsecond // 1000:03d}",
        "ffffff": f"{dt.microsecond:06d}",
        "timestamp": str(int(dt.timestamp())),
        "unix_ms": str(int(dt.timestamp() * 1000)),
    }
    text = str(config.get("template", "{YYYY}-{MM}-{DD} {HH}:{mm}:{ss}") or "")
    for key in sorted(values.keys(), key=len, reverse=True):
        text = text.replace("{" + key + "}", values[key])
    return text


def parse_new_columns_specs(config):
    text = str(config.get("columns_text", "") or "")
    strip_name = bool(config.get("strip_column_name", True))
    allow_empty = bool(config.get("allow_empty_name", False))
    value_mode = config.get("value_mode", "统一默认值")
    default_value = str(config.get("default_value", "") or "")
    specs = []
    auto_index = 1
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip() if strip_name else raw_line
        if line == "":
            continue
        if "=" in line:
            name, value = line.split("=", 1)
            name = name.strip() if strip_name else name
            if value_mode == "按列配置值":
                fill_value = value
            elif value_mode == "空值":
                fill_value = ""
            else:
                fill_value = default_value
        else:
            name = line
            fill_value = "" if value_mode == "空值" else default_value
        if name == "":
            if allow_empty:
                name = f"新字段{auto_index}"
                auto_index += 1
            else:
                raise ValueError("新建列节点存在空字段名。可删除空行，或勾选允许空字段名自动命名。")
        specs.append((name, "" if fill_value is None else str(fill_value)))
    if not specs:
        raise ValueError("新建列节点没有填写任何字段名。")
    return specs


def apply_new_columns_node(headers, rows, config):
    headers = list(headers)
    new_rows = normalize_rows(rows, len(headers))
    specs = parse_new_columns_specs(config)
    conflict_mode = config.get("conflict_mode", "自动改名")
    added = 0
    overwritten = 0
    skipped = 0
    output_names = []

    for name, fill_value in specs:
        if name in headers:
            if conflict_mode == "自动改名":
                final_name = get_unique_header(name, headers)
                headers.append(final_name)
                for row in new_rows:
                    row.append(fill_value)
                added += 1
                output_names.append(final_name)
            elif conflict_mode == "跳过已有字段":
                skipped += 1
                continue
            elif conflict_mode == "覆盖已有字段":
                idx = headers.index(name)
                for row in new_rows:
                    row[idx] = fill_value
                overwritten += 1
                output_names.append(name)
            elif conflict_mode == "存在则报错":
                raise ValueError(f"新建列节点字段已存在：{name}")
            else:
                raise ValueError(f"未知同名字段处理方式：{conflict_mode}")
        else:
            headers.append(name)
            for row in new_rows:
                row.append(fill_value)
            added += 1
            output_names.append(name)

    shown = ", ".join(output_names[:8])
    if len(output_names) > 8:
        shown += f" ... 共{len(output_names)}个"
    return headers, new_rows, f"新建列完成：新增 {added} 列，覆盖 {overwritten} 列，跳过 {skipped} 列；字段：{shown}"


def apply_current_datetime_column_node(headers, rows, config, now_func=None):
    headers = list(headers)
    new_rows = normalize_rows(rows, len(headers))
    output_mode = config.get("output_mode", "生成新字段")
    now_func = now_func or datetime.now

    if output_mode == "覆盖已有字段":
        target = str(config.get("target_field", "")).strip()
        if not target:
            raise ValueError("新建日期时间列节点选择了覆盖已有字段，但未选择覆盖字段。")
        output_idx = field_index(headers, target)
        output_name = headers[output_idx]
    else:
        output_name = get_unique_header(config.get("new_field", "当前日期时间"), headers)
        headers.append(output_name)
        output_idx = len(headers) - 1
        for row in new_rows:
            row.append("")

    fixed_time = now_func()
    same_time = config.get("time_mode", "整次运行固定同一时间") == "整次运行固定同一时间"
    changed = 0
    sample = ""
    for row in new_rows:
        dt = fixed_time if same_time else now_func()
        value = render_current_datetime_template(dt, config)
        row[output_idx] = value
        if sample == "":
            sample = value
        changed += 1

    if not new_rows:
        sample = render_current_datetime_template(fixed_time, config)
    return headers, new_rows, f"新建日期时间列完成：字段【{output_name}】，写入 {changed} 行，示例：{sample}"


def normalize_datetime_source_text(value):
    return normalize_datetime_text(value)


def parse_format_int(value, name, allow_zero=False):
    try:
        n = int(str(value).strip())
    except Exception:
        raise ValueError(f"{name} 必须是整数。")
    if allow_zero:
        if n < 0:
            raise ValueError(f"{name} 不能小于 0。")
    else:
        if n <= 0:
            raise ValueError(f"{name} 必须大于 0。")
    return n


def slice_by_position(text, start, length, base, name):
    length = parse_format_int(length, f"{name}长度", allow_zero=True)
    if length == 0:
        return ""
    start = parse_format_int(start, f"{name}起始")
    idx = start - 1 if base == "从1开始" else start
    if idx < 0 or idx + length > len(text):
        raise ValueError(f"{name}位置越界")
    return text[idx:idx + length]


def complete_format_year(value, config):
    return complete_year(value, config)


def build_date_parts(year, month, day, config):
    parsed_year = complete_format_year(year, config)
    try:
        parsed_month = int(str(month).strip())
        parsed_day = int(str(day).strip())
    except Exception:
        raise ValueError("月/日不是数字")
    try:
        datetime(parsed_year, parsed_month, parsed_day)
    except Exception:
        raise ValueError(f"日期无效：{parsed_year:04d}-{parsed_month:02d}-{parsed_day:02d}")
    return {"year": parsed_year, "month": parsed_month, "day": parsed_day}


def build_time_parts(hour, minute="0", second="0"):
    try:
        parsed_hour = int(str(hour).strip())
        parsed_minute = int(str(minute).strip()) if str(minute).strip() != "" else 0
        parsed_second = int(str(second).strip()) if str(second).strip() != "" else 0
    except Exception:
        raise ValueError("时/分/秒不是数字")
    if not (0 <= parsed_hour <= 23):
        raise ValueError("小时超出范围 0-23")
    if not (0 <= parsed_minute <= 59):
        raise ValueError("分钟超出范围 0-59")
    if not (0 <= parsed_second <= 59):
        raise ValueError("秒超出范围 0-59")
    return {"hour": parsed_hour, "minute": parsed_minute, "second": parsed_second}


def parse_date_fixed(text, config):
    base = config.get("position_base", "从1开始")
    year = slice_by_position(text, config.get("year_start", "1"), config.get("year_len", "2"), base, "年")
    month = slice_by_position(text, config.get("month_start", "3"), config.get("month_len", "2"), base, "月")
    day = slice_by_position(text, config.get("day_start", "5"), config.get("day_len", "2"), base, "日")
    return build_date_parts(year, month, day, config)


def parse_time_fixed(text, config):
    base = config.get("position_base", "从1开始")
    hour = slice_by_position(text, config.get("hour_start", "1"), config.get("hour_len", "2"), base, "时")
    minute = slice_by_position(text, config.get("minute_start", "3"), config.get("minute_len", "2"), base, "分")
    second = slice_by_position(text, config.get("second_start", "5"), config.get("second_len", "0"), base, "秒")
    return build_time_parts(hour, minute, second or "0")


def split_by_config_delimiter(text, kind, config):
    if kind == "date":
        mode = config.get("date_delimiter", "自动识别")
        custom = config.get("custom_date_delimiter", "-")
        if mode == "年/月/日":
            return re.findall(r"\d+", text)
        if mode == "自定义":
            if custom == "":
                raise ValueError("自定义日期分隔符不能为空")
            return text.split(custom)
        if mode == "自动识别":
            return re.findall(r"\d+", text)
        return text.split(mode)

    mode = config.get("time_delimiter", "自动识别")
    custom = config.get("custom_time_delimiter", ":")
    if mode == "时/分/秒":
        return re.findall(r"\d+", text)
    if mode == "自定义":
        if custom == "":
            raise ValueError("自定义时间分隔符不能为空")
        return text.split(custom)
    if mode == "自动识别":
        return re.findall(r"\d+", text)
    return text.split(mode)


def parse_date_delimited(text, config):
    parts = [part.strip() for part in split_by_config_delimiter(text, "date", config) if str(part).strip() != ""]
    if len(parts) < 3:
        raise ValueError("日期分隔后不足 3 段")
    order = config.get("date_order", "年-月-日")
    if order == "月-日-年":
        month, day, year = parts[0], parts[1], parts[2]
    elif order == "日-月-年":
        day, month, year = parts[0], parts[1], parts[2]
    else:
        year, month, day = parts[0], parts[1], parts[2]
    check_ambiguous_delimited_date(parts, order, config)
    return build_date_parts(year, month, day, config)


def parse_time_delimited(text, config):
    parts = [part.strip() for part in split_by_config_delimiter(text, "time", config) if str(part).strip() != ""]
    if len(parts) < 2:
        raise ValueError("时间分隔后不足 2 段")
    hour = parts[0]
    minute = parts[1]
    second = parts[2] if len(parts) >= 3 else "0"
    return build_time_parts(hour, minute, second)


def parse_date_auto_common(text, config):
    return shared_parse_date_auto_common(text, config)


def parse_time_auto_common(text, config):
    normalized = normalize_datetime_source_text(text)
    match = re.search(r"(?<!\d)(\d{1,2})\s*[:时]\s*(\d{1,2})(?:\s*[:分]\s*(\d{1,2}))?(?:\s*秒)?(?!\d)", normalized)
    if match:
        return build_time_parts(match.group(1), match.group(2), match.group(3) or "0")
    match = re.search(r"(?<!\d)(\d{6})(?!\d)", normalized)
    if match:
        value = match.group(1)
        return build_time_parts(value[:2], value[2:4], value[4:6])
    match = re.search(r"(?<!\d)(\d{4})(?!\d)", normalized)
    if match:
        value = match.group(1)
        return build_time_parts(value[:2], value[2:4], "0")
    raise ValueError("未识别到常见时间格式")


def parse_format_datetime_value(date_text, time_text, config):
    date_text = normalize_datetime_source_text(date_text)
    time_text = normalize_datetime_source_text(time_text)
    if config.get("strip_value", True):
        date_text = date_text.strip()
        time_text = time_text.strip()
    parse_type = config.get("parse_type", "日期")
    structure = config.get("input_structure", "固定位置")
    parts = {"year": None, "month": None, "day": None, "hour": None, "minute": None, "second": None}
    if parse_type in ("日期", "日期时间"):
        if structure == "固定位置":
            date_parts = parse_date_fixed(date_text, config)
        elif structure == "分隔符":
            date_parts = parse_date_delimited(date_text, config)
        else:
            date_parts = parse_date_auto_common(date_text, config)
        parts.update(date_parts)
    if parse_type in ("时间", "日期时间"):
        time_source = time_text if (parse_type == "日期时间" and config.get("use_separate_time_field", False)) else date_text
        if structure == "固定位置":
            time_parts = parse_time_fixed(time_source, config)
        elif structure == "分隔符":
            time_parts = parse_time_delimited(time_source, config)
        else:
            time_parts = parse_time_auto_common(time_source, config)
        parts.update(time_parts)
    return parts


def render_format_template(parts, template):
    year = parts.get("year")
    month = parts.get("month")
    day = parts.get("day")
    hour = parts.get("hour")
    minute = parts.get("minute")
    second = parts.get("second")
    values = {
        "YYYY": f"{year:04d}" if year is not None else "",
        "YY": f"{year % 100:02d}" if year is not None else "",
        "MM": f"{month:02d}" if month is not None else "",
        "M": str(month) if month is not None else "",
        "DD": f"{day:02d}" if day is not None else "",
        "D": str(day) if day is not None else "",
        "HH": f"{hour:02d}" if hour is not None else "",
        "H": str(hour) if hour is not None else "",
        "mm": f"{minute:02d}" if minute is not None else "",
        "m": str(minute) if minute is not None else "",
        "ss": f"{second:02d}" if second is not None else "",
        "s": str(second) if second is not None else "",
    }
    text = str(template or "")
    for key in sorted(values.keys(), key=len, reverse=True):
        text = text.replace("{" + key + "}", values[key])
    return text


def format_output_value(parts, config):
    parse_type = config.get("parse_type", "日期")
    if parse_type == "时间":
        template = config.get("time_output_template", "{HH}:{mm}")
    elif parse_type == "日期时间":
        template = config.get("datetime_output_template", "{YYYY}-{MM}-{DD} {HH}:{mm}")
    else:
        template = config.get("output_template", "{YYYY}-{MM}-{DD}")
    return render_format_template(parts, template)


def apply_unmatched_format_value(original, status, config):
    mode = config.get("unmatched_mode", "留空")
    if mode == "保留原值":
        return original, status
    if mode == "填写固定值":
        return str(config.get("unmatched_fixed", "未匹配")), status
    if mode == "跳过该行":
        return "", "跳过"
    return "", status


def build_format_component_columns(parts, parse_type, prefix):
    prefix = str(prefix or "解析").strip() or "解析"
    values = []
    if parse_type in ("日期", "日期时间"):
        values.extend([
            (f"{prefix}年", f"{parts.get('year'):04d}" if parts.get("year") is not None else ""),
            (f"{prefix}月", f"{parts.get('month'):02d}" if parts.get("month") is not None else ""),
            (f"{prefix}日", f"{parts.get('day'):02d}" if parts.get("day") is not None else ""),
        ])
    if parse_type in ("时间", "日期时间"):
        values.extend([
            (f"{prefix}时", f"{parts.get('hour'):02d}" if parts.get("hour") is not None else ""),
            (f"{prefix}分", f"{parts.get('minute'):02d}" if parts.get("minute") is not None else ""),
            (f"{prefix}秒", f"{parts.get('second'):02d}" if parts.get("second") is not None else ""),
        ])
    return values


def get_datetime_parse_warning(original, config, parts):
    warnings = []
    if config.get("input_structure") == "分隔符":
        values = [
            item.strip()
            for item in split_by_config_delimiter(
                normalize_datetime_source_text(original),
                "date",
                config,
            )
            if str(item).strip()
        ]
        order = config.get("date_order", "年-月-日")
        warning = ambiguous_delimited_date_warning(values, order)
        if warning and ambiguous_date_policy(config) != "允许":
            warnings.append(warning)
    if config.get("year_rule") == "不补全":
        year = parts.get("year")
        if year is not None and int(year) < 1000:
            warnings.append("年份未补全且不足四位")
    return "；".join(warnings)


def apply_format_datetime_node(headers, rows, config):
    source_idx = field_index(headers, config.get("source_field", ""))
    time_idx = None
    if config.get("parse_type") == "日期时间" and config.get("use_separate_time_field", False):
        time_idx = field_index(headers, config.get("time_source_field", ""))
    headers = list(headers)
    new_rows = normalize_rows(rows, len(headers))
    output_mode = config.get("output_mode", "生成新字段")
    parse_type = config.get("parse_type", "日期")
    main_field = str(config.get("new_field", "标准日期")).strip() or "标准日期"
    status_enabled = bool(config.get("output_status", True))
    status_field = str(config.get("status_field", "格式解析状态")).strip() or "格式解析状态"
    output_indexes = []
    status_idx = None

    if output_mode == "生成新字段":
        main_field = get_unique_header(main_field, headers)
        headers.append(main_field)
        output_indexes.append(("main", len(headers) - 1, main_field))
        for row in new_rows:
            row.append("")
    elif output_mode == "生成多个字段":
        main_field = get_unique_header(main_field, headers)
        headers.append(main_field)
        output_indexes.append(("main", len(headers) - 1, main_field))
        for row in new_rows:
            row.append("")
        for base_name, _dummy in build_format_component_columns({}, parse_type, config.get("component_prefix", "解析")):
            name = get_unique_header(base_name, headers)
            headers.append(name)
            output_indexes.append((base_name, len(headers) - 1, name))
            for row in new_rows:
                row.append("")
    else:
        output_indexes.append(("main", source_idx, headers[source_idx]))

    if status_enabled:
        status_name = get_unique_header(status_field, headers)
        headers.append(status_name)
        status_idx = len(headers) - 1
        for row in new_rows:
            row.append("")

    changed = 0
    skipped = 0
    failed = 0
    for row in new_rows:
        original = safe_cell(row, source_idx)
        time_text = safe_cell(row, time_idx) if time_idx is not None else original
        try:
            parts = parse_format_datetime_value(original, time_text, config)
            out_value = format_output_value(parts, config)
            warning = get_datetime_parse_warning(original, config, parts)
            status = "成功但存在歧义：" + warning if warning else "成功"
        except Exception as exc:
            failed += 1
            out_value, status = apply_unmatched_format_value(original, str(exc), config)
            parts = {"year": None, "month": None, "day": None, "hour": None, "minute": None, "second": None}

        if status == "跳过":
            skipped += 1
            if status_idx is not None:
                row[status_idx] = "跳过"
            continue

        component_values = dict(build_format_component_columns(parts, parse_type, config.get("component_prefix", "解析")))
        for kind, idx, name in output_indexes:
            if kind == "main":
                row[idx] = out_value
            else:
                row[idx] = component_values.get(kind, "")
        if status_idx is not None:
            row[status_idx] = status
        changed += 1

    return headers, new_rows, f"格式规范化完成：写入 {changed} 行，失败 {failed} 行，跳过 {skipped} 行"


def apply_unmatched_extract(text, status, config):
    mode = config.get("unmatched_mode", "留空")
    if mode == "留空":
        return "", status
    if mode == "保留原值":
        return text, status
    if mode == "填写固定值":
        return str(config.get("unmatched_fixed", "未匹配")), status
    if mode == "跳过该行":
        return "", "跳过"
    return "", status


def post_extract_result(result, config):
    result = "" if result is None else str(result)
    if config.get("strip_result", True):
        result = result.strip()
    return result


def extract_one_value(original, config):
    text = "" if original is None else str(original)
    method = config.get("method", "正则提取")
    case_sensitive = bool(config.get("case_sensitive", True))

    def norm(value):
        return value if case_sensitive else value.lower()

    try:
        if method == "正则提取":
            pattern = config.get("regex_pattern", "")
            if not pattern:
                raise ValueError("正则表达式不能为空。")
            flags = 0 if case_sensitive else re.IGNORECASE
            group_index = parse_int(config.get("regex_group", "0"), "提取分组")
            if config.get("regex_find_all", False):
                results = []
                for match in re.finditer(pattern, text, flags):
                    try:
                        results.append(match.group(group_index))
                    except IndexError:
                        return apply_unmatched_extract(text, "分组不存在", config)
                if not results:
                    return apply_unmatched_extract(text, "未匹配", config)
                return post_extract_result(str(config.get("regex_joiner", ";")).join(results), config), "成功"
            match = re.search(pattern, text, flags)
            if not match:
                return apply_unmatched_extract(text, "未匹配", config)
            try:
                return post_extract_result(match.group(group_index), config), "成功"
            except IndexError:
                return apply_unmatched_extract(text, "分组不存在", config)

        if method == "固定位置提取":
            start = parse_int(config.get("start_pos", "1"), "起始位置")
            length = parse_int(config.get("extract_len", "1"), "提取长度")
            start_idx = start - 1 if config.get("position_base", "从1开始") == "从1开始" else start
            if start_idx < 0 or start_idx >= len(text):
                return apply_unmatched_extract(text, "越界", config)
            return post_extract_result(text[start_idx:start_idx + length], config), "成功"

        if method == "从左取N位":
            n = parse_int(config.get("n_chars", "1"), "N")
            return post_extract_result(text[:max(n, 0)], config), "成功"

        if method == "从右取N位":
            n = parse_int(config.get("n_chars", "1"), "N")
            return post_extract_result(text[-n:] if n > 0 else "", config), "成功"

        if method == "按分隔符提取":
            delimiter = str(config.get("delimiter", "-"))
            if delimiter == "":
                raise ValueError("分隔符不能为空。")
            parts = text.split(delimiter)
            if config.get("ignore_empty_part", False):
                parts = [part for part in parts if part != ""]
            part_index = parse_int(config.get("part_index", "1"), "取第几段")
            if part_index == 0:
                raise ValueError("段序号不能为0。")
            idx = part_index - 1 if part_index > 0 else part_index
            if idx < -len(parts) or idx >= len(parts):
                return apply_unmatched_extract(text, "越界", config)
            return post_extract_result(parts[idx], config), "成功"

        if method == "前后关键字之间提取":
            start_key = str(config.get("before_key", ""))
            end_key = str(config.get("after_key", ""))
            if not start_key or not end_key:
                raise ValueError("开始关键字和结束关键字不能为空。")
            occurrence = parse_int(config.get("between_occurrence", "1"), "第几个匹配")
            search_text = norm(text)
            search_start = norm(start_key)
            search_end = norm(end_key)
            pos = 0
            found = None
            for _ in range(occurrence):
                start_pos = search_text.find(search_start, pos)
                if start_pos < 0:
                    return apply_unmatched_extract(text, "未匹配", config)
                content_start = start_pos + len(start_key)
                end_pos = search_text.find(search_end, content_start)
                if end_pos < 0:
                    return apply_unmatched_extract(text, "未匹配", config)
                found = text[content_start:end_pos]
                pos = end_pos + len(end_key)
            return post_extract_result(found, config), "成功"

        if method in ["指定字符前提取", "指定字符后提取"]:
            marker = str(config.get("marker", "-"))
            if marker == "":
                raise ValueError("指定字符不能为空。")
            search_text = norm(text)
            search_marker = norm(marker)
            idx = (
                search_text.rfind(search_marker)
                if config.get("find_mode", "第一次出现") == "最后一次出现"
                else search_text.find(search_marker)
            )
            if idx < 0:
                return apply_unmatched_extract(text, "未匹配", config)
            if method == "指定字符前提取":
                return post_extract_result(text[:idx], config), "成功"
            return post_extract_result(text[idx + len(marker):], config), "成功"

        if method == "删除前缀":
            prefix = str(config.get("prefix", ""))
            if prefix == "":
                raise ValueError("前缀不能为空。")
            if norm(text).startswith(norm(prefix)):
                return post_extract_result(text[len(prefix):], config), "成功"
            return apply_unmatched_extract(text, "未匹配", config)

        if method == "删除后缀":
            suffix = str(config.get("suffix", ""))
            if suffix == "":
                raise ValueError("后缀不能为空。")
            if norm(text).endswith(norm(suffix)):
                return post_extract_result(text[:-len(suffix)], config), "成功"
            return apply_unmatched_extract(text, "未匹配", config)

        raise ValueError(f"未知提取方式：{method}")
    except re.error as exc:
        raise ValueError(f"正则错误：{exc}") from exc


def apply_extract_node(headers, rows, config):
    idx = field_index(headers, config.get("source_field", ""))
    headers = list(headers)
    new_rows = normalize_rows(rows, len(headers))
    changed = 0
    skipped = 0

    if config.get("output_mode", "生成新字段") == "生成新字段":
        new_header = get_unique_header(config.get("new_field", "提取结果"), headers)
        headers.append(new_header)
        for row in new_rows:
            extracted, status = extract_one_value(safe_cell(row, idx), config)
            if status == "跳过":
                skipped += 1
                row.append("")
            else:
                row.append(extracted)
                changed += 1
    else:
        for row in new_rows:
            extracted, status = extract_one_value(safe_cell(row, idx), config)
            if status == "跳过":
                skipped += 1
                continue
            row[idx] = extracted
            changed += 1

    return headers, new_rows, f"写入 {changed} 行，跳过 {skipped} 行"
