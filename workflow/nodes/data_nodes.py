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
from workflow.nodes.filter_execution_nodes import (
    apply_filter_node,
    build_plan_filter_right_index,
    eval_plan_condition_record,
    eval_plan_join_rule_record,
    get_plan_filter_hash_join_rules,
    iter_plan_filter_join_candidates,
    plan_filter_condition_dependencies,
    record_passes_plan_conditions,
    record_passes_plan_join_rules,
    record_survives_available_plan_conditions,
    resolve_plan_condition_value,
)
from workflow.nodes.table_edit_nodes import (
    apply_copy_column_node,
    apply_copy_row_node,
    apply_delete_columns_node,
    apply_delete_rows_node,
    apply_move_columns_node,
    parse_row_spec_to_indexes,
)

