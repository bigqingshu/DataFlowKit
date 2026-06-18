# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for data/runtime compatibility wrappers."""

from core.data_utils import (
    make_unique_headers_for_append as core_make_unique_headers_for_append,
    normalize_rows as core_normalize_rows,
    safe_cell as core_safe_cell,
)
from workflow import group_field_analysis as workflow_group_field_analysis
from workflow.nodes.data_common import (
    compare_values as workflow_compare_values,
    ensure_column_count as workflow_ensure_column_count,
    ensure_field_exists as workflow_ensure_field_exists,
    ensure_row_count as workflow_ensure_row_count,
    ensure_target_cell_limit as workflow_ensure_target_cell_limit,
    field_index as workflow_field_index,
    get_positive_int as workflow_get_positive_int,
    get_unique_header as workflow_get_unique_header,
    last_non_empty_row_index_by_field as workflow_last_non_empty_row_index_by_field,
    parse_int as workflow_parse_int,
    parse_row_number as workflow_parse_row_number,
    row_is_empty as workflow_row_is_empty,
)
from workflow.nodes.data_nodes import (
    add_plan_filter_required_field as workflow_add_plan_filter_required_field,
    build_plan_filter_right_index as workflow_build_plan_filter_right_index,
    collect_plan_filter_required_fields as workflow_collect_plan_filter_required_fields,
    eval_plan_condition_record as workflow_eval_plan_condition_record,
    eval_plan_join_rule_record as workflow_eval_plan_join_rule_record,
    get_plan_filter_config_warnings as workflow_get_plan_filter_config_warnings,
    get_plan_filter_field_owner as workflow_get_plan_filter_field_owner,
    get_plan_filter_hash_join_availability as workflow_get_plan_filter_hash_join_availability,
    get_plan_filter_hash_join_rules as workflow_get_plan_filter_hash_join_rules,
    get_plan_filter_output_base_headers as workflow_get_plan_filter_output_base_headers,
    get_plan_filter_output_header_conflicts as workflow_get_plan_filter_output_header_conflicts,
    get_plan_filter_output_headers as workflow_get_plan_filter_output_headers,
    get_required_columns_for_plan_table as workflow_get_required_columns_for_plan_table,
    iter_plan_filter_join_candidates as workflow_iter_plan_filter_join_candidates,
    make_current_table_records as workflow_make_current_table_records,
    make_unique_plan_headers as workflow_make_unique_plan_headers,
    normalize_filter_condition_value_source as workflow_normalize_filter_condition_value_source,
    normalize_plan_filter_config_field_references as workflow_normalize_plan_filter_config_field_references,
    normalize_plan_filter_field_reference as workflow_normalize_plan_filter_field_reference,
    plan_filter_condition_dependencies as workflow_plan_filter_condition_dependencies,
    plan_filter_field_belongs_to_table as workflow_plan_filter_field_belongs_to_table,
    record_passes_plan_conditions as workflow_record_passes_plan_conditions,
    record_passes_plan_join_rules as workflow_record_passes_plan_join_rules,
    record_survives_available_plan_conditions as workflow_record_survives_available_plan_conditions,
    resolve_plan_condition_value as workflow_resolve_plan_condition_value,
)
from workflow.nodes.match_value_output_nodes import (
    match_value_output_column_match as workflow_match_value_output_column_match,
)
from workflow.nodes.datetime_format_nodes import (
    apply_unmatched_format_value as workflow_apply_unmatched_format_value,
    build_date_parts as workflow_build_date_parts,
    build_format_component_columns as workflow_build_format_component_columns,
    build_time_parts as workflow_build_time_parts,
    complete_format_year as workflow_complete_format_year,
    format_output_value as workflow_format_output_value,
    get_datetime_parse_warning as workflow_get_datetime_parse_warning,
    normalize_datetime_source_text as workflow_normalize_datetime_source_text,
    parse_date_auto_common as workflow_parse_date_auto_common,
    parse_date_delimited as workflow_parse_date_delimited,
    parse_date_fixed as workflow_parse_date_fixed,
    parse_format_datetime_value as workflow_parse_format_datetime_value,
    parse_format_int as workflow_parse_format_int,
    parse_time_auto_common as workflow_parse_time_auto_common,
    parse_time_delimited as workflow_parse_time_delimited,
    parse_time_fixed as workflow_parse_time_fixed,
    render_format_template as workflow_render_format_template,
    slice_by_position as workflow_slice_by_position,
    split_by_config_delimiter as workflow_split_by_config_delimiter,
)
from workflow.nodes.extract_nodes import (
    apply_unmatched_extract as workflow_apply_unmatched_extract,
    extract_one_value as workflow_extract_one_value,
    post_extract_result as workflow_post_extract_result,
)
from workflow.nodes.fill_nodes import (
    format_sequence_value as workflow_format_sequence_value,
    get_config_cell_value as workflow_get_config_cell_value,
    get_cycle_source_values_by_config as workflow_get_cycle_source_values_by_config,
    get_fill_targets as workflow_get_fill_targets,
    get_source_area_values_by_config as workflow_get_source_area_values_by_config,
    get_source_column_values_by_config as workflow_get_source_column_values_by_config,
    get_source_row_multi_field_values_by_config as workflow_get_source_row_multi_field_values_by_config,
    resolve_area_end_row_index as workflow_resolve_area_end_row_index,
    resolve_sequence_count_by_source as workflow_resolve_sequence_count_by_source,
    resolve_start_row_index_by_mode as workflow_resolve_start_row_index_by_mode,
    should_write_cell as workflow_should_write_cell,
)
from workflow.nodes.row_mapping_nodes import get_row_mapping_end_index as workflow_get_row_mapping_end_index
from workflow.nodes.new_column_nodes import (
    parse_new_columns_specs as workflow_parse_new_columns_specs,
    render_current_datetime_template as workflow_render_current_datetime_template,
)
from workflow.nodes.numeric_column_nodes import (
    format_numeric_column_result as workflow_format_numeric_column_result,
    get_numeric_node_row_indexes as workflow_get_numeric_node_row_indexes,
    numeric_node_fallback_value as workflow_numeric_node_fallback_value,
    parse_numeric_value_for_column_op as workflow_parse_numeric_value_for_column_op,
)
from workflow.nodes.file_nodes import (
    get_or_add_column_index as workflow_get_or_add_column_index,
    is_hidden_path as workflow_is_hidden_path,
    parse_extensions_filter as workflow_parse_extensions_filter,
)
from workflow.nodes.group_nodes import (
    build_group_input_table as workflow_build_group_input_table,
    make_group_child_context as workflow_make_group_child_context,
    normalize_group_sqlite_mode as workflow_normalize_group_sqlite_mode,
    normalize_group_transit_conflict_mode as workflow_normalize_group_transit_conflict_mode,
    parse_group_input_fields as workflow_parse_group_input_fields,
)
from workflow.nodes.loop_nodes import (
    evaluate_loop_condition as workflow_evaluate_loop_condition,
    find_loop_judge_index as workflow_find_loop_judge_index,
    find_loop_start_index as workflow_find_loop_start_index,
    loop_last_non_empty_row_index as workflow_loop_last_non_empty_row_index,
)
from workflow.nodes.transit_nodes import (
    append_headers_rows as workflow_append_headers_rows,
    make_unique_transit_name as workflow_make_unique_transit_name,
)
from workflow.nodes.writeback_nodes import (
    build_writeback_full_structure_rows_for_sqlite as workflow_build_writeback_full_structure_rows_for_sqlite,
    compare_writeback_values as workflow_compare_writeback_values,
)


class WorkflowDataRuntimeMixin:
    """Compatibility methods used by data nodes and workflow runtime helpers."""

    def loop_last_non_empty_row_index(self, headers, rows, field):
        return workflow_loop_last_non_empty_row_index(headers, rows, field)

    def evaluate_loop_condition(self, headers, rows, config, context=None, loop_state=None):
        return workflow_evaluate_loop_condition(headers, rows, config, loop_state=loop_state)

    def find_loop_start_index(self, loop_id, current_idx, nodes=None):
        node_list = nodes if nodes is not None else self.nodes
        return workflow_find_loop_start_index(loop_id, current_idx, node_list)

    def find_loop_judge_index(self, loop_id, start_idx, end_idx, nodes=None):
        node_list = nodes if nodes is not None else self.nodes
        return workflow_find_loop_judge_index(loop_id, start_idx, end_idx, node_list)

    def format_logs(self, logs):
        if not logs:
            return ""
        last = logs[-3:]
        text = "  最近节点：" + "；".join(last)
        return text[:500]

    def parse_group_input_fields(self, config):
        return workflow_parse_group_input_fields(config)

    def parse_new_column_names_for_group_analysis(self, text, strip_name=True, allow_empty=False):
        return workflow_group_field_analysis.parse_new_column_names_for_group_analysis(
            text,
            strip_name=strip_name,
            allow_empty=allow_empty,
        )

    def add_group_field_ref(self, target, value):
        return workflow_group_field_analysis.add_group_field_ref(target, value)

    def add_group_field_refs_from_dict_list(self, target, items, keys):
        return workflow_group_field_analysis.add_group_field_refs_from_dict_list(target, items, keys)

    def classify_group_filter_field_reference(self, field, extra_tables=None):
        return workflow_group_field_analysis.classify_group_filter_field_reference(
            field,
            extra_tables=extra_tables,
        )

    def get_group_filter_external_output_fields(self, config, context=None):
        return workflow_group_field_analysis.get_group_filter_external_output_fields(
            self,
            config,
            context=context,
        )

    def analyze_group_filter_field_io(self, config, context=None):
        return workflow_group_field_analysis.analyze_group_filter_field_io(
            self,
            config,
            context=context,
        )

    def analyze_group_inner_node_field_io(self, node, context=None):
        return workflow_group_field_analysis.analyze_group_inner_node_field_io(
            self,
            node,
            context=context,
        )

    def collect_group_fields_from_nested_config(self, target, value, field_keys=None):
        return workflow_group_field_analysis.collect_group_fields_from_nested_config(
            target,
            value,
            field_keys=field_keys,
        )

    def infer_group_input_fields_from_nodes(self, nodes, context=None):
        return workflow_group_field_analysis.infer_group_input_fields_from_nodes(
            self,
            nodes,
            context=context,
        )

    def format_group_input_infer_details(self, inferred, details, limit=20):
        return workflow_group_field_analysis.format_group_input_infer_details(
            inferred,
            details,
            limit=limit,
        )

    def normalize_group_transit_conflict_mode(self, mode):
        return workflow_normalize_group_transit_conflict_mode(mode)

    def normalize_group_sqlite_mode(self, mode):
        return workflow_normalize_group_sqlite_mode(mode)

    def build_group_input_table(self, source_headers, source_rows, config):
        return workflow_build_group_input_table(source_headers, source_rows, config)

    def make_group_child_context(self, parent_context, config):
        return workflow_make_group_child_context(parent_context, config)

    def field_index(self, headers, field):
        return workflow_field_index(headers, field)

    def safe_cell(self, row, idx):
        return core_safe_cell(row, idx)

    def normalize_rows(self, rows, col_count):
        return core_normalize_rows(rows, col_count)

    def compare_values(self, text, op, value, case_sensitive=True):
        return workflow_compare_values(text, op, value, case_sensitive=case_sensitive)

    def parse_extensions_filter(self, text_value):
        return workflow_parse_extensions_filter(text_value)

    def is_hidden_path(self, path):
        return workflow_is_hidden_path(path)

    def check_workflow_cancelled(self, context=None):
        """长循环节点内部调用：用户点击取消后，在安全检查点停止。"""
        cancel_event = (context or {}).get("cancel_event")
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("用户取消后台执行")

    def check_workflow_cancelled_periodically(self, context, index, interval=500):
        if index == 0 or index % max(1, int(interval)) == 0:
            self.check_workflow_cancelled(context)

    def report_workflow_node_progress(self, context=None, current=None, total=None, message="", node_name=""):
        """长循环节点内部调用：通过后台 Queue 回传节点内行级/项目级进度。"""
        callback = (context or {}).get("progress_callback")
        if not callable(callback):
            return
        try:
            callback({
                "type": "node_progress",
                "node_name": node_name or "当前节点",
                "current": current,
                "total": total,
                "message": message or "处理中",
            })
        except Exception:
            pass

    def get_or_add_column_index(self, headers, rows, column_name):
        return workflow_get_or_add_column_index(headers, rows, column_name)

    def parse_int(self, value, name):
        return workflow_parse_int(value, name)

    def safe_int(self, value, default=0):
        try:
            return int(str(value).strip())
        except Exception:
            return default

    def apply_unmatched_extract(self, text, status, config):
        return workflow_apply_unmatched_extract(text, status, config)

    def post_extract_result(self, result, config):
        return workflow_post_extract_result(result, config)

    def extract_one_value(self, original, config):
        return workflow_extract_one_value(original, config)

    def get_unique_header(self, base_name, headers):
        return workflow_get_unique_header(base_name, headers)

    def normalize_datetime_source_text(self, value):
        return workflow_normalize_datetime_source_text(value)

    def parse_format_int(self, value, name, allow_zero=False):
        return workflow_parse_format_int(value, name, allow_zero=allow_zero)

    def slice_by_position(self, text, start, length, base, name):
        return workflow_slice_by_position(text, start, length, base, name)

    def complete_format_year(self, value, config):
        return workflow_complete_format_year(value, config)

    def build_date_parts(self, year, month, day, config):
        return workflow_build_date_parts(year, month, day, config)

    def build_time_parts(self, hour, minute="0", second="0"):
        return workflow_build_time_parts(hour, minute, second)

    def parse_date_fixed(self, text, config):
        return workflow_parse_date_fixed(text, config)

    def parse_time_fixed(self, text, config):
        return workflow_parse_time_fixed(text, config)

    def split_by_config_delimiter(self, text, kind, config):
        return workflow_split_by_config_delimiter(text, kind, config)

    def parse_date_delimited(self, text, config):
        return workflow_parse_date_delimited(text, config)

    def parse_time_delimited(self, text, config):
        return workflow_parse_time_delimited(text, config)

    def parse_date_auto_common(self, text, config):
        return workflow_parse_date_auto_common(text, config)

    def parse_time_auto_common(self, text, config):
        return workflow_parse_time_auto_common(text, config)

    def parse_format_datetime_value(self, date_text, time_text, config):
        return workflow_parse_format_datetime_value(date_text, time_text, config)

    def render_format_template(self, parts, template):
        return workflow_render_format_template(parts, template)

    def format_output_value(self, parts, config):
        return workflow_format_output_value(parts, config)

    def apply_unmatched_format_value(self, original, status, config):
        return workflow_apply_unmatched_format_value(original, status, config)

    def build_format_component_columns(self, parts, parse_type, prefix):
        return workflow_build_format_component_columns(parts, parse_type, prefix)

    def get_datetime_parse_warning(self, original, config, parts):
        return workflow_get_datetime_parse_warning(original, config, parts)

    def render_current_datetime_template(self, dt, config):
        return workflow_render_current_datetime_template(dt, config)

    def parse_new_columns_specs(self, config):
        return workflow_parse_new_columns_specs(config)

    def ensure_field_exists(self, headers, rows, field_name):
        return workflow_ensure_field_exists(headers, rows, field_name)

    def ensure_row_count(self, rows, row_count, col_count):
        return workflow_ensure_row_count(
            rows,
            row_count,
            col_count,
            max_expanded_rows=self.MAX_EXPANDED_ROWS,
        )

    def ensure_target_cell_limit(self, row_count, col_count):
        return workflow_ensure_target_cell_limit(
            row_count,
            col_count,
            max_target_cells=self.MAX_TARGET_CELLS,
        )

    def ensure_column_count(self, headers, rows, col_count, base_name="区域复制列"):
        return workflow_ensure_column_count(headers, rows, col_count, base_name)

    def parse_row_number(self, value, name="行号"):
        return workflow_parse_row_number(value, name)

    def get_config_cell_value(self, headers, rows, config, target_row_idx=None):
        return workflow_get_config_cell_value(headers, rows, config, target_row_idx=target_row_idx)

    def resolve_start_row_index_by_mode(self, headers, rows, target_field, config):
        return workflow_resolve_start_row_index_by_mode(headers, rows, target_field, config)

    def get_source_column_values_by_config(self, headers, rows, config):
        return workflow_get_source_column_values_by_config(headers, rows, config)

    def get_cycle_source_values_by_config(self, headers, rows, config, multi_field=False):
        return workflow_get_cycle_source_values_by_config(headers, rows, config, multi_field=multi_field)

    def get_source_row_multi_field_values_by_config(self, headers, rows, config):
        return workflow_get_source_row_multi_field_values_by_config(headers, rows, config)

    def get_source_area_values_by_config(self, headers, rows, config):
        return workflow_get_source_area_values_by_config(headers, rows, config)

    def resolve_sequence_count_by_source(self, headers, rows, config):
        return workflow_resolve_sequence_count_by_source(headers, rows, config)

    def row_is_empty(self, row, col_count):
        return workflow_row_is_empty(row, col_count)

    def last_non_empty_row_index_by_field(self, headers, rows, field_name):
        return workflow_last_non_empty_row_index_by_field(headers, rows, field_name)

    def resolve_area_end_row_index(self, headers, rows, config):
        return workflow_resolve_area_end_row_index(headers, rows, config)

    def get_fill_targets(self, headers, rows, target_field, start_row_value, direction, end_mode, count_value,
                         end_row_value, end_field_value, reference_field_value="", allow_expand_rows=True,
                         allow_expand_cols=False):
        return workflow_get_fill_targets(
            headers,
            rows,
            target_field,
            start_row_value,
            direction,
            end_mode,
            count_value,
            end_row_value,
            end_field_value,
            reference_field_value=reference_field_value,
            allow_expand_rows=allow_expand_rows,
            allow_expand_cols=allow_expand_cols,
            max_expanded_rows=self.MAX_EXPANDED_ROWS,
            max_target_cells=self.MAX_TARGET_CELLS,
        )

    def should_write_cell(self, current_value, overwrite_rule):
        return workflow_should_write_cell(current_value, overwrite_rule)

    def format_sequence_value(self, value, config):
        return workflow_format_sequence_value(value, config)

    def get_positive_int(self, value, default_value):
        return workflow_get_positive_int(value, default_value)

    def get_plan_filter_available_fields(self, headers, extra_tables, context=None):
        fields = [f"当前表.{h}" for h in headers]
        transit_tables = (context or {}).get("transit_tables", {})
        for table in extra_tables:
            try:
                if str(table).startswith("中转:"):
                    name = str(table).split(":", 1)[1]
                    item = transit_tables.get(name, {})
                    for col in item.get("headers", []):
                        fields.append(f"{table}.{col}")
                else:
                    for col in self.get_workflow_sqlite_columns(table, context):
                        fields.append(f"{table}.{col}")
            except Exception:
                continue
        return fields

    def normalize_plan_filter_field_reference(self, field, headers, extra_tables=None):
        return workflow_normalize_plan_filter_field_reference(field, headers, extra_tables)

    def normalize_plan_filter_config_field_references(self, config, headers, extra_tables=None):
        return workflow_normalize_plan_filter_config_field_references(config, headers, extra_tables)

    def get_plan_filter_output_base_headers(self, lookup_fields, headers):
        return workflow_get_plan_filter_output_base_headers(lookup_fields, headers)

    def get_plan_filter_output_headers(self, lookup_fields, headers):
        return workflow_get_plan_filter_output_headers(lookup_fields, headers)

    def get_plan_filter_output_header_conflicts(self, lookup_fields, headers):
        return workflow_get_plan_filter_output_header_conflicts(lookup_fields, headers)

    def plan_filter_field_belongs_to_table(self, field, table_name):
        return workflow_plan_filter_field_belongs_to_table(field, table_name)

    def get_plan_filter_field_owner(self, field, headers, extra_tables):
        return workflow_get_plan_filter_field_owner(field, headers, extra_tables)

    def get_plan_filter_hash_join_availability(self, headers, extra_tables, join_rules, join_logic):
        return workflow_get_plan_filter_hash_join_availability(headers, extra_tables, join_rules, join_logic)

    def get_plan_filter_config_warnings(self, headers, extra_tables, conditions, join_rules, join_logic):
        return workflow_get_plan_filter_config_warnings(headers, extra_tables, conditions, join_rules, join_logic)

    def add_plan_filter_required_field(self, field, headers, extra_tables, current_headers, table_fields):
        return workflow_add_plan_filter_required_field(field, headers, extra_tables, current_headers, table_fields)

    def collect_plan_filter_required_fields(self, headers, extra_tables, conditions, join_rules, output_fields, final_fields):
        return workflow_collect_plan_filter_required_fields(
            headers, extra_tables, conditions, join_rules, output_fields, final_fields
        )

    def get_required_columns_for_plan_table(self, table_name, columns, required_fields):
        return workflow_get_required_columns_for_plan_table(table_name, columns, required_fields)

    def make_current_table_records(self, headers, rows, required_headers=None):
        return workflow_make_current_table_records(headers, rows, required_headers)

    def normalize_filter_condition_value_source(self, cond):
        return workflow_normalize_filter_condition_value_source(cond)

    def resolve_plan_condition_value(self, record, cond):
        return workflow_resolve_plan_condition_value(record, cond)

    def eval_plan_condition_record(self, record, cond):
        return workflow_eval_plan_condition_record(record, cond)

    def eval_plan_join_rule_record(self, record, rule):
        return workflow_eval_plan_join_rule_record(record, rule)

    def record_passes_plan_conditions(self, record, conditions, logic):
        return workflow_record_passes_plan_conditions(record, conditions, logic)

    def plan_filter_condition_dependencies(self, cond):
        return workflow_plan_filter_condition_dependencies(cond)

    def record_survives_available_plan_conditions(self, record, conditions, logic):
        return workflow_record_survives_available_plan_conditions(record, conditions, logic)

    def record_passes_plan_join_rules(self, record, join_rules, logic="AND"):
        return workflow_record_passes_plan_join_rules(record, join_rules, logic)

    def get_plan_filter_hash_join_rules(self, table_name, join_rules, join_logic, right_records):
        return workflow_get_plan_filter_hash_join_rules(table_name, join_rules, join_logic, right_records)

    def build_plan_filter_right_index(self, right_records, hash_rules):
        return workflow_build_plan_filter_right_index(right_records, hash_rules)

    def iter_plan_filter_join_candidates(self, left_record, right_records, hash_rules, right_index, missing_key_records):
        return workflow_iter_plan_filter_join_candidates(
            left_record, right_records, hash_rules, right_index, missing_key_records
        )

    def get_row_mapping_end_index(self, rows, start_idx, config, col_count):
        return workflow_get_row_mapping_end_index(rows, start_idx, config, col_count)

    def make_unique_transit_name(self, base_name, transit_tables):
        return workflow_make_unique_transit_name(base_name, transit_tables)

    def append_headers_rows(self, old_headers, old_rows, new_headers, new_rows):
        return workflow_append_headers_rows(old_headers, old_rows, new_headers, new_rows)

    def compare_writeback_values(self, left, op, right):
        return workflow_compare_writeback_values(left, op, right)

    def build_writeback_full_structure_rows_for_sqlite(self, headers, rows, config, target_columns):
        return workflow_build_writeback_full_structure_rows_for_sqlite(headers, rows, config, target_columns)

    def match_value_output_column_match(self, source_value, lookup_value, mode):
        return workflow_match_value_output_column_match(source_value, lookup_value, mode)

    def make_unique_plan_headers(self, headers):
        return workflow_make_unique_plan_headers(headers)

    def parse_numeric_value_for_column_op(self, value):
        return workflow_parse_numeric_value_for_column_op(value)

    def format_numeric_column_result(self, value, config):
        return workflow_format_numeric_column_result(value, config)

    def get_numeric_node_row_indexes(self, headers, rows, config):
        return workflow_get_numeric_node_row_indexes(headers, rows, config)

    def numeric_node_fallback_value(self, original_value, policy, fixed_value, fail_text):
        return workflow_numeric_node_fallback_value(original_value, policy, fixed_value, fail_text)

    def make_unique_headers_for_append(self, existing_headers, new_headers):
        """给追加字段生成不重复字段名。"""
        return core_make_unique_headers_for_append(existing_headers, new_headers)
