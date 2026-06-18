# -*- coding: utf-8 -*-
"""Pure data-shaping workflow nodes."""

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
from workflow.nodes.new_column_nodes import (
    apply_current_datetime_column_node,
    apply_new_columns_node,
    parse_new_columns_specs,
    render_current_datetime_template,
)
from workflow.nodes.datetime_format_nodes import (
    apply_format_datetime_node,
    apply_unmatched_format_value,
    build_date_parts,
    build_format_component_columns,
    build_time_parts,
    complete_format_year,
    format_output_value,
    get_datetime_parse_warning,
    normalize_datetime_source_text,
    parse_date_auto_common,
    parse_date_delimited,
    parse_date_fixed,
    parse_format_datetime_value,
    parse_format_int,
    parse_time_auto_common,
    parse_time_delimited,
    parse_time_fixed,
    render_format_template,
    slice_by_position,
    split_by_config_delimiter,
)
from workflow.nodes.dedupe_nodes import apply_dedupe_node
from workflow.nodes.extract_nodes import (
    apply_extract_node,
    apply_unmatched_extract,
    extract_one_value,
    post_extract_result,
)
from workflow.nodes.fill_nodes import (
    apply_area_fill_node,
    apply_fill_value_node,
    apply_sequence_fill_node,
    format_sequence_value,
    get_config_cell_value,
    get_cycle_source_values_by_config,
    get_fill_targets,
    get_source_area_values_by_config,
    get_source_column_values_by_config,
    get_source_row_multi_field_values_by_config,
    resolve_area_end_row_index,
    resolve_sequence_count_by_source,
    resolve_start_row_index_by_mode,
    should_write_cell,
)
from workflow.nodes.replace_nodes import (
    apply_replace_node,
    replace_pair_count_for_row,
    replace_row_index_for_policy,
    replace_source_value,
)
from workflow.nodes.row_mapping_nodes import (
    apply_row_data_mapping_node,
    get_row_mapping_end_index,
)
from workflow.nodes.merge_rename_nodes import (
    apply_merge_node,
    apply_rename_columns_node,
)
from workflow.nodes.match_value_output_nodes import (
    apply_match_value_output_field_name_node,
    match_value_output_column_match,
)
from workflow.nodes.filter_plan_nodes import (
    add_plan_filter_required_field,
    build_filter_config_probe_result,
    build_filter_runtime_plan,
    choose_plan_filter_lookup_fields,
    collect_plan_filter_required_fields,
    get_plan_filter_config_warnings,
    get_plan_filter_field_owner,
    get_plan_filter_hash_join_availability,
    get_plan_filter_output_base_headers,
    get_plan_filter_output_header_conflicts,
    get_plan_filter_output_headers,
    get_required_columns_for_plan_table,
    make_current_table_records,
    make_unique_plan_headers,
    normalize_filter_condition_value_source,
    normalize_plan_filter_config_field_references,
    normalize_plan_filter_field_reference,
    plan_filter_field_belongs_to_table,
)
from workflow.nodes.table_edit_nodes import (
    apply_copy_column_node,
    apply_copy_row_node,
    apply_delete_columns_node,
    apply_delete_rows_node,
    apply_move_columns_node,
    parse_row_spec_to_indexes,
)


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

