# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for plugin configuration UI wrappers."""

from workflow.plugin_config_helpers import plugin_config_transit_reuse_note
from workflow import plugin_dynamic_config_ui
from workflow.plugin_config_ui import (
    build_plugin_input_tables_section as build_plugin_input_tables_section_ui,
    build_plugin_node_config as build_plugin_node_config_ui,
    build_plugin_run_environment_section as build_plugin_run_environment_section_ui,
    open_plugin_input_spec_editor as open_plugin_input_spec_editor_ui,
    refresh_plugin_input_listbox as refresh_plugin_input_listbox_ui,
)
from workflow.plugin_schema_config_ui import (
    build_plugin_output_and_log_section as build_plugin_output_and_log_section_ui,
    build_plugin_schema_parameter_controls as build_plugin_schema_parameter_controls_ui,
)


class PluginConfigWindowMixin:
    """Compatibility methods used by plugin config UI modules."""

    def plugin_config_context_with_live_transit(self, transit_context=None, include_rows=False):
        return plugin_dynamic_config_ui.plugin_config_context_with_live_transit(
            self,
            transit_context=transit_context,
            include_rows=include_rows,
        )

    def plugin_config_transit_reuse_note(self, transit_context=None):
        return plugin_config_transit_reuse_note(transit_context)

    def get_plugin_dynamic_parameter_choices_for_config(
        self,
        item,
        config,
        params,
        spec,
        key,
        headers,
        current_rows=None,
        transit_context=None,
        input_table_headers=None,
    ):
        return plugin_dynamic_config_ui.get_plugin_dynamic_parameter_choices_for_config(
            self,
            item,
            config,
            params,
            spec,
            key,
            headers,
            current_rows=current_rows,
            transit_context=transit_context,
            input_table_headers=input_table_headers,
        )

    def run_plugin_custom_config_window(
        self,
        item,
        config,
        params,
        headers,
        current_rows=None,
        transit_context=None,
        dynamic_param_controls=None,
        refresh_dynamic_controls=None,
    ):
        return plugin_dynamic_config_ui.run_plugin_custom_config_window(
            self,
            item,
            config,
            params,
            headers,
            current_rows=current_rows,
            transit_context=transit_context,
            dynamic_param_controls=dynamic_param_controls,
            refresh_dynamic_controls=refresh_dynamic_controls,
        )

    def refresh_plugin_dynamic_config_controls(self, controls, set_param, get_choices):
        return plugin_dynamic_config_ui.refresh_plugin_dynamic_config_controls(
            controls,
            set_param,
            get_choices,
        )

    def build_plugin_run_environment_section(self, frame, config, item, plugin_id, start_row=3):
        return build_plugin_run_environment_section_ui(
            self,
            frame,
            config,
            item,
            plugin_id,
            start_row=start_row,
        )

    def refresh_plugin_input_listbox(self, input_lb, config):
        return refresh_plugin_input_listbox_ui(input_lb, config)

    def open_plugin_input_spec_editor(
        self,
        config,
        index,
        sqlite_tables,
        transit_names,
        refresh_input_lb,
        refresh_plugin_dynamic_controls,
    ):
        return open_plugin_input_spec_editor_ui(
            self,
            config,
            index,
            sqlite_tables,
            transit_names,
            refresh_input_lb,
            refresh_plugin_dynamic_controls,
        )

    def build_plugin_input_tables_section(
        self,
        frame,
        config,
        row,
        sqlite_tables,
        transit_names,
        refresh_plugin_dynamic_controls,
    ):
        return build_plugin_input_tables_section_ui(
            self,
            frame,
            config,
            row,
            sqlite_tables,
            transit_names,
            refresh_plugin_dynamic_controls,
        )

    def create_plugin_dynamic_config_context(self, item, config, params, headers, transit_context, current_rows, dynamic_param_controls):
        return plugin_dynamic_config_ui.create_plugin_dynamic_config_context(
            self,
            item,
            config,
            params,
            headers,
            transit_context,
            current_rows,
            dynamic_param_controls,
        )

    def build_plugin_schema_parameter_controls(
        self,
        frame,
        schema,
        config,
        params,
        headers,
        row,
        dynamic_param_controls,
        dynamic_context,
    ):
        return build_plugin_schema_parameter_controls_ui(
            self,
            frame,
            schema,
            config,
            params,
            headers,
            row,
            dynamic_param_controls,
            dynamic_context,
        )

    def build_plugin_output_and_log_section(
        self,
        frame,
        config,
        item,
        params,
        headers,
        current_rows,
        transit_context,
        dynamic_param_controls,
        refresh_plugin_dynamic_controls,
        row,
    ):
        return build_plugin_output_and_log_section_ui(
            self,
            frame,
            config,
            item,
            params,
            headers,
            current_rows,
            transit_context,
            dynamic_param_controls,
            refresh_plugin_dynamic_controls,
            row,
        )

    def build_plugin_node_config(self, config, headers, transit_context=None, current_rows=None):
        return build_plugin_node_config_ui(
            self,
            config,
            headers,
            transit_context=transit_context,
            current_rows=current_rows,
        )
