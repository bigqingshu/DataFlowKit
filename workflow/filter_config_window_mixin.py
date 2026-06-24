# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for advanced filter configuration UI wrappers."""

from ui.workflow.config.filter_config_ui import (
    build_filter_condition_action_buttons as build_filter_condition_action_buttons_ui,
    build_filter_condition_section as build_filter_condition_section_ui,
    build_filter_config as build_filter_config_ui,
    build_filter_header_risk_section as build_filter_header_risk_section_ui,
    build_filter_join_action_buttons as build_filter_join_action_buttons_ui,
    build_filter_join_section as build_filter_join_section_ui,
    build_filter_output_action_buttons as build_filter_output_action_buttons_ui,
    build_filter_output_section as build_filter_output_section_ui,
    build_filter_source_table_section as build_filter_source_table_section_ui,
    edit_filter_condition_cell as edit_filter_condition_cell_ui,
    filter_tree_rows as filter_tree_rows_ui,
    invert_output_fields as invert_output_fields_ui,
    refresh_filter_actual_output_text as refresh_filter_actual_output_text_ui,
    refresh_filter_condition_value_input as refresh_filter_condition_value_input_ui,
    refresh_filter_field_sources as refresh_filter_field_sources_ui,
    refresh_filter_risk_text as refresh_filter_risk_text_ui,
    replace_filter_tree_rows as replace_filter_tree_rows_ui,
    select_all_output_fields as select_all_output_fields_ui,
    select_current_table_output_fields as select_current_table_output_fields_ui,
    sync_filter_output_fields as sync_filter_output_fields_ui,
)


class FilterConfigWindowMixin:
    """Compatibility methods used by advanced filter UI modules."""

    def build_filter_header_risk_section(self, frame, start_row=0):
        return build_filter_header_risk_section_ui(self, frame, start_row=start_row)

    def build_filter_source_table_section(self, frame, config, headers, selected_tables, transit_context, sync_extra_tables, start_row=2):
        return build_filter_source_table_section_ui(
            self,
            frame,
            config,
            headers,
            selected_tables,
            transit_context,
            sync_extra_tables,
            start_row=start_row,
        )

    def build_filter_condition_section(self, frame, config, all_fields, start_row=3):
        return build_filter_condition_section_ui(self, frame, config, all_fields, start_row=start_row)

    def build_filter_join_section(self, frame, config, all_fields, current_fields, start_row=4):
        return build_filter_join_section_ui(self, frame, config, all_fields, current_fields, start_row=start_row)

    def build_filter_output_section(self, frame, config, all_fields, start_row=5):
        return build_filter_output_section_ui(self, frame, config, all_fields, start_row=start_row)

    def refresh_filter_risk_text(self, headers, config, risk_var, risk_label):
        return refresh_filter_risk_text_ui(self, headers, config, risk_var, risk_label)

    def refresh_filter_condition_value_input(self, field_state, value_source_var, value_var, value_combo):
        return refresh_filter_condition_value_input_ui(field_state, value_source_var, value_var, value_combo)

    def filter_tree_rows(self, tree):
        return filter_tree_rows_ui(tree)

    def replace_filter_tree_rows(self, tree, rows):
        return replace_filter_tree_rows_ui(tree, rows)

    def edit_filter_condition_cell(self, event, cond_tree, cond_edit_mode, sync_conditions_from_tree):
        return edit_filter_condition_cell_ui(event, cond_tree, cond_edit_mode, sync_conditions_from_tree)

    def build_filter_condition_action_buttons(self, condition_section, config, refresh_filter_risk_text, headers=None, field_state=None):
        return build_filter_condition_action_buttons_ui(
            self,
            condition_section,
            config,
            headers or [],
            field_state or {"all_values": []},
            refresh_filter_risk_text,
        )

    def build_filter_join_action_buttons(self, join_section, config, refresh_filter_risk_text, headers=None, field_state=None):
        return build_filter_join_action_buttons_ui(
            self,
            join_section,
            config,
            headers or [],
            field_state or {"all_values": []},
            refresh_filter_risk_text,
        )

    def refresh_filter_actual_output_text(self, out_list, actual_output_var, headers, field_state, config):
        return refresh_filter_actual_output_text_ui(out_list, actual_output_var, headers, field_state, config)

    def sync_filter_output_fields(self, out_list, actual_output_var, headers, field_state, config):
        return sync_filter_output_fields_ui(out_list, actual_output_var, headers, field_state, config)

    def build_filter_output_action_buttons(self, output_section, config, headers, field_state):
        return build_filter_output_action_buttons_ui(self, output_section, config, headers, field_state)

    def refresh_filter_field_sources(
        self,
        headers,
        config,
        transit_context,
        field_state,
        source_section,
        condition_section,
        join_section,
        output_section,
        sync_output_fields,
        refresh_condition_value_input,
        refresh_filter_risk_text,
    ):
        return refresh_filter_field_sources_ui(
            self,
            headers,
            config,
            transit_context,
            field_state,
            source_section,
            condition_section,
            join_section,
            output_section,
            sync_output_fields,
            refresh_condition_value_input,
            refresh_filter_risk_text,
        )

    def build_filter_config(self, config, headers, transit_context=None):
        return build_filter_config_ui(self, config, headers, transit_context=transit_context)

    def select_all_output_fields(self, listbox, config):
        return select_all_output_fields_ui(listbox, config)

    def invert_output_fields(self, listbox, config):
        return invert_output_fields_ui(listbox, config)

    def select_current_table_output_fields(self, listbox, config):
        return select_current_table_output_fields_ui(listbox, config)
