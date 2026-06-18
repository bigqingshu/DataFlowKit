# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for workflow config builder wrappers."""

from workflow import output_node_runtime as workflow_output_node_runtime
from workflow.basic_data_config_ui import (
    build_current_datetime_column_config as workflow_build_current_datetime_column_config_ui,
    build_extract_config as workflow_build_extract_config_ui,
    build_format_datetime_config as workflow_build_format_datetime_config_ui,
    build_new_columns_config as workflow_build_new_columns_config_ui,
    build_replace_config as workflow_build_replace_config_ui,
)
from workflow.control_flow_config_ui import (
    anchor_id_from_choice as workflow_anchor_id_from_choice_ui,
    build_condition_check_config as workflow_build_condition_check_config_ui,
    build_conditional_jump_config as workflow_build_conditional_jump_config_ui,
    build_jump_anchor_config as workflow_build_jump_anchor_config_ui,
    build_loop_judge_config as workflow_build_loop_judge_config_ui,
    build_loop_start_config as workflow_build_loop_start_config_ui,
    build_unconditional_jump_config as workflow_build_unconditional_jump_config_ui,
    jump_anchor_choices as workflow_jump_anchor_choices_ui,
    set_anchor_var_to_config as workflow_set_anchor_var_to_config_ui,
)
from ui.workflow.config.dedupe_config_ui import build_dedupe_config as workflow_build_dedupe_config_ui
from ui.workflow.config.file_config_ui import (
    build_batch_rename_config as workflow_build_batch_rename_config_ui,
    build_file_list_config as workflow_build_file_list_config_ui,
)
from workflow.match_value_output_config_ui import (
    build_match_value_output_field_name_config as workflow_build_match_value_output_field_name_config_ui,
)
from workflow.merge_config_ui import (
    build_merge_config as workflow_build_merge_config_ui,
    display_to_sep_value as workflow_display_to_sep_value,
    ensure_separator_count as workflow_ensure_separator_count_ui,
    preview_plan_separator as workflow_preview_plan_separator_ui,
    refresh_merge_separator_ui as workflow_refresh_merge_separator_ui,
    sep_value_to_display as workflow_sep_value_to_display,
    separator_to_input_text as workflow_separator_to_input_text,
)
from ui.workflow.config.numeric_column_config_ui import (
    build_numeric_column_config as workflow_build_numeric_column_config_ui,
)
from ui.workflow.config.rename_columns_config_ui import (
    build_rename_columns_config as workflow_build_rename_columns_config_ui,
)
from workflow.row_data_mapping_config_ui import (
    build_row_data_mapping_config as workflow_build_row_data_mapping_config_ui,
)
from ui.workflow.config.save_transit_config_ui import (
    build_save_transit_config as workflow_build_save_transit_config_ui,
)
from workflow.selected_columns_write_config_ui import (
    build_selected_columns_write_config as workflow_build_selected_columns_write_config_ui,
)
from workflow.nodes.data_nodes import parse_separator_text as workflow_parse_separator_text
from workflow.nodes.selected_columns_nodes import (
    apply_selected_columns_to_memory_table as workflow_apply_selected_columns_to_memory_table,
    get_selected_columns_write_selected_fields as workflow_get_selected_columns_write_selected_fields,
    make_selected_columns_target_fields as workflow_make_selected_columns_target_fields,
    normalize_selected_columns_write_mode as workflow_normalize_selected_columns_write_mode,
    selected_columns_should_write as workflow_selected_columns_should_write,
)
from workflow.table_edit_config_ui import (
    build_area_fill_config as workflow_build_area_fill_config_ui,
    build_copy_column_config as workflow_build_copy_column_config_ui,
    build_copy_row_config as workflow_build_copy_row_config_ui,
    build_delete_columns_config as workflow_build_delete_columns_config_ui,
    build_delete_rows_config as workflow_build_delete_rows_config_ui,
    build_fill_value_config as workflow_build_fill_value_config_ui,
    build_move_columns_config as workflow_build_move_columns_config_ui,
    build_sequence_fill_config as workflow_build_sequence_fill_config_ui,
)
from workflow.writeback_config_ui import (
    build_writeback_config as workflow_build_writeback_config_ui,
)


class WorkflowConfigBuilderMixin:
    """Compatibility methods used by workflow configuration UI modules."""

    def build_loop_start_config(self, config, headers, transit_context=None):
        return workflow_build_loop_start_config_ui(self, config, headers, transit_context=transit_context)

    def build_loop_judge_config(self, config, headers):
        return workflow_build_loop_judge_config_ui(self, config, headers)

    def jump_anchor_choices(self):
        return workflow_jump_anchor_choices_ui(self.nodes)

    def anchor_id_from_choice(self, value):
        return workflow_anchor_id_from_choice_ui(value)

    def set_anchor_var_to_config(self, var, config, key):
        return workflow_set_anchor_var_to_config_ui(var, config, key)

    def build_jump_anchor_config(self, config):
        return workflow_build_jump_anchor_config_ui(self, config)

    def build_unconditional_jump_config(self, config):
        return workflow_build_unconditional_jump_config_ui(self, config)

    def build_condition_check_config(self, config, headers):
        return workflow_build_condition_check_config_ui(self, config, headers)

    def build_conditional_jump_config(self, config):
        return workflow_build_conditional_jump_config_ui(self, config)

    def build_file_list_config(self, config):
        return workflow_build_file_list_config_ui(self, config)

    def build_batch_rename_config(self, config, headers):
        return workflow_build_batch_rename_config_ui(self, config, headers)

    def build_replace_config(self, config, headers):
        return workflow_build_replace_config_ui(self, config, headers)

    def build_extract_config(self, config, headers):
        return workflow_build_extract_config_ui(self, config, headers)

    def build_format_datetime_config(self, config, headers):
        return workflow_build_format_datetime_config_ui(self, config, headers)

    def build_current_datetime_column_config(self, config, headers):
        return workflow_build_current_datetime_column_config_ui(self, config, headers)

    def build_new_columns_config(self, config, headers):
        return workflow_build_new_columns_config_ui(self, config, headers)

    def build_merge_config(self, config, headers):
        return workflow_build_merge_config_ui(self, config, headers)

    def build_match_value_output_field_name_config(self, config, headers, transit_context=None):
        return workflow_build_match_value_output_field_name_config_ui(self, config, headers, transit_context)

    def build_numeric_column_config(self, config, headers):
        return workflow_build_numeric_column_config_ui(self, config, headers)

    def build_rename_columns_config(self, config, headers):
        return workflow_build_rename_columns_config_ui(self, config, headers)

    def ensure_separator_count(self, config):
        return workflow_ensure_separator_count_ui(config)

    def parse_separator_text(self, text):
        return workflow_parse_separator_text(text)

    def separator_to_input_text(self, text):
        return workflow_separator_to_input_text(text)

    def sep_value_to_display(self, sep):
        return workflow_sep_value_to_display(sep, self.SEPARATOR_OPTIONS)

    def display_to_sep_value(self, display, custom):
        return workflow_display_to_sep_value(display, custom)

    def preview_plan_separator(self, parent, left_name, right_name, combo_var, custom_var):
        return workflow_preview_plan_separator_ui(self, left_name, right_name, combo_var, custom_var)

    def refresh_merge_separator_ui(self, parent, config):
        return workflow_refresh_merge_separator_ui(self, parent, config)

    def build_row_data_mapping_config(self, config, headers):
        return workflow_build_row_data_mapping_config_ui(self, config, headers)

    def build_save_transit_config(self, config, headers):
        return workflow_build_save_transit_config_ui(self, config, headers)

    def build_selected_columns_write_config(self, config, headers, idx=None, transit_context=None):
        return workflow_build_selected_columns_write_config_ui(self, config, headers, idx, transit_context)

    def get_selected_columns_write_selected_fields(self, config, source_headers):
        return workflow_get_selected_columns_write_selected_fields(config, source_headers)

    def make_selected_columns_target_fields(self, config, selected_fields):
        return workflow_make_selected_columns_target_fields(config, selected_fields)

    def read_selected_columns_source_table(self, config, current_headers, current_rows, context=None):
        return workflow_output_node_runtime.read_selected_columns_source_table(
            self,
            config,
            current_headers,
            current_rows,
            context,
        )

    def read_selected_columns_target_table(self, config, context=None, current_headers=None, current_rows=None):
        return workflow_output_node_runtime.read_selected_columns_target_table(
            self,
            config,
            context,
            current_headers,
            current_rows,
        )

    def selected_columns_should_write(self, old_value, new_value, overwrite_rule):
        return workflow_selected_columns_should_write(old_value, new_value, overwrite_rule)

    def normalize_selected_columns_write_mode(self, write_mode):
        return workflow_normalize_selected_columns_write_mode(write_mode)

    def build_selected_columns_write_preview(self, config, current_headers, current_rows, context=None):
        return workflow_output_node_runtime.build_selected_columns_write_preview(
            self,
            config,
            current_headers,
            current_rows,
            context,
        )

    def apply_selected_columns_to_memory_table(self, target_headers, target_rows, selected_target_headers, selected_rows, config):
        return workflow_apply_selected_columns_to_memory_table(
            target_headers,
            target_rows,
            selected_target_headers,
            selected_rows,
            config,
        )

    def get_selected_columns_write_payload(self, config, current_headers, current_rows, context=None):
        return workflow_output_node_runtime.get_selected_columns_write_payload(
            self,
            config,
            current_headers,
            current_rows,
            context,
        )

    def apply_selected_columns_write_current_table(self, headers, rows, config, target_fields, selected_rows):
        return workflow_output_node_runtime.apply_selected_columns_write_current_table(
            self,
            headers,
            rows,
            config,
            target_fields,
            selected_rows,
        )

    def apply_selected_columns_write_transit_table(self, headers, rows, config, context, target_name, target_fields, selected_rows):
        return workflow_output_node_runtime.apply_selected_columns_write_transit_table(
            self,
            headers,
            rows,
            config,
            context,
            target_name,
            target_fields,
            selected_rows,
        )

    def apply_selected_columns_write_sqlite_table(self, headers, rows, config, context, target_name, target_fields, selected_rows):
        return workflow_output_node_runtime.apply_selected_columns_write_sqlite_table(
            self,
            headers,
            rows,
            config,
            context,
            target_name,
            target_fields,
            selected_rows,
        )

    def build_writeback_config(self, config, headers):
        return workflow_build_writeback_config_ui(self, config, headers)

    def build_copy_column_config(self, config, headers):
        return workflow_build_copy_column_config_ui(self, config, headers)

    def build_copy_row_config(self, config, headers):
        return workflow_build_copy_row_config_ui(self, config, headers)

    def build_delete_rows_config(self, config, headers):
        return workflow_build_delete_rows_config_ui(self, config, headers)

    def build_fill_value_config(self, config, headers):
        return workflow_build_fill_value_config_ui(self, config, headers)

    def build_sequence_fill_config(self, config, headers):
        return workflow_build_sequence_fill_config_ui(self, config, headers)

    def build_area_fill_config(self, config, headers):
        return workflow_build_area_fill_config_ui(self, config, headers)

    def build_dedupe_config(self, config, headers):
        return workflow_build_dedupe_config_ui(self, config, headers)

    def build_delete_columns_config(self, config, headers):
        return workflow_build_delete_columns_config_ui(self, config, headers)

    def build_move_columns_config(self, config, headers):
        return workflow_build_move_columns_config_ui(self, config, headers)
