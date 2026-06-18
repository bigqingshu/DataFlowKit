# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for group/subworkflow config UI wrappers."""

import sys
from tkinter import messagebox as tk_messagebox

from ui.workflow.config import group_config_ui
from workflow.nodes.group_nodes import (
    add_group_inner_node,
    apply_group_inner_node_list_action,
    apply_group_template_config,
    group_inner_node_type_values,
    group_source_headers_for_mapping,
    make_group_inner_node,
    parse_group_inner_node_json,
    unique_keep_order,
)


def _window_messagebox(window):
    module = sys.modules.get(window.__class__.__module__)
    return getattr(module, "messagebox", tk_messagebox)


class GroupConfigWindowMixin:
    """Compatibility methods used by group config UI modules."""

    def unique_keep_order(self, values):
        return unique_keep_order(values)

    def get_group_config_source_headers(self, source_type, headers, transit_context=None, transit_name="", sqlite_table=""):
        sqlite_columns = []
        if source_type == "SQLite表" and sqlite_table:
            try:
                sqlite_columns = self.get_workflow_sqlite_columns(
                    sqlite_table,
                    context=transit_context if isinstance(transit_context, dict) else None,
                )
            except Exception:
                sqlite_columns = []
        return group_source_headers_for_mapping(
            source_type,
            headers,
            (transit_context or {}).get("transit_tables", {}) if isinstance(transit_context, dict) else {},
            transit_name,
            sqlite_columns,
        )

    def save_group_inner_node_json_text(self, config, index, text):
        nodes = config.setdefault("nodes", [])
        if index is None or index < 0 or index >= len(nodes):
            raise ValueError("请先选择一个组内节点。")
        nodes[index] = parse_group_inner_node_json(text)
        return index

    def load_group_template_into_config(self, config):
        data = self.load_group_template_dialog()
        if data is None:
            return False
        apply_group_template_config(config, self.group_config_from_template_data(data))
        self.rebuild_current_config()
        return True

    def get_group_inner_node_type_values(self):
        return group_inner_node_type_values(self.get_node_type_values())

    def make_group_inner_node(self, node_type):
        return make_group_inner_node(
            node_type,
            plugin_display_map=getattr(self, "plugin_display_map", {}),
            plugin_registry=getattr(self, "plugin_registry", {}),
            plugin_config_factory=self.default_config_for_plugin,
            default_name_factory=self.default_name_for_node,
            default_config_factory=self.default_config_for_type,
        )

    def add_group_inner_node_to_config(self, config, node_type):
        _, index = add_group_inner_node(
            config,
            node_type,
            plugin_display_map=getattr(self, "plugin_display_map", {}),
            plugin_registry=getattr(self, "plugin_registry", {}),
            plugin_config_factory=self.default_config_for_plugin,
            default_name_factory=self.default_name_for_node,
            default_config_factory=self.default_config_for_type,
        )
        return index

    def apply_group_inner_node_list_action_to_config(self, config, index, action, delta=0):
        nodes, select_idx = apply_group_inner_node_list_action(
            config.setdefault("nodes", []),
            index,
            action,
            delta=delta,
        )
        config["nodes"] = nodes
        return select_idx

    def build_group_input_source_controls(self, input_frame, config, transit_context=None):
        return group_config_ui.build_group_input_source_controls(
            self,
            input_frame,
            config,
            transit_context=transit_context,
        )

    def build_group_input_fields_controls(self, input_frame, config, refresh_mapping):
        return group_config_ui.build_group_input_fields_controls(self, input_frame, config, refresh_mapping)

    def build_group_mapping_tree_control(self, input_frame):
        return group_config_ui.build_group_mapping_tree_control(input_frame)

    def build_group_mapping_edit_controls(self, input_frame):
        return group_config_ui.build_group_mapping_edit_controls(input_frame)

    def build_group_mapping_action_buttons(
        self,
        map_edit,
        apply_mapping,
        auto_mapping,
        use_source_headers,
        infer_inputs,
    ):
        return group_config_ui.build_group_mapping_action_buttons(
            map_edit,
            apply_mapping,
            auto_mapping,
            use_source_headers,
            infer_inputs,
        )

    def build_group_input_mapping_section(self, frame, config, headers, transit_context=None, row=2):
        return group_config_ui.build_group_input_mapping_section(
            self,
            frame,
            config,
            headers,
            transit_context=transit_context,
            row=row,
        )

    def build_group_output_section(self, frame, config, row=3):
        return group_config_ui.build_group_output_section(self, frame, config, row=row)

    def refresh_group_source_field_combo(self, source_field_combo, source_field_var, source_headers):
        return group_config_ui.refresh_group_source_field_combo(
            source_field_combo,
            source_field_var,
            source_headers,
        )

    def sync_group_mapping_edit_from_selected(
        self,
        config,
        mapping_tree,
        selected_input_var,
        source_field_var,
        default_value_var,
        refresh_source_fields,
    ):
        return group_config_ui.sync_group_mapping_edit_from_selected(
            config,
            mapping_tree,
            selected_input_var,
            source_field_var,
            default_value_var,
            refresh_source_fields,
        )

    def refresh_group_selected_input_combo(self, config, selected_input_combo, selected_input_var, sync_detail=None):
        return group_config_ui.refresh_group_selected_input_combo(
            config,
            selected_input_combo,
            selected_input_var,
            sync_detail=sync_detail,
        )

    def refresh_group_mapping_tree(self, config, mapping_tree, refresh_selected_inputs):
        return group_config_ui.refresh_group_mapping_tree(config, mapping_tree, refresh_selected_inputs)

    def apply_group_mapping_from_controls(self, config, selected_input_var, source_field_var, default_value_var, refresh_mapping):
        return group_config_ui.apply_group_mapping_from_controls(
            config,
            selected_input_var,
            source_field_var,
            default_value_var,
            refresh_mapping,
            messagebox_module=_window_messagebox(self),
        )

    def auto_group_mapping_by_name_from_source(self, config, get_source_headers, refresh_mapping):
        return group_config_ui.auto_group_mapping_by_name_from_source(config, get_source_headers, refresh_mapping)

    def use_group_source_headers_as_inputs(self, config, get_source_headers, set_input_fields_text, refresh_mapping):
        return group_config_ui.use_group_source_headers_as_inputs(
            config,
            get_source_headers,
            set_input_fields_text,
            refresh_mapping,
        )

    def create_group_input_mapping_callbacks(
        self,
        config,
        transit_context,
        get_source_headers,
        mapping_tree,
        selected_input_combo,
        selected_input_var,
        source_field_combo,
        source_field_var,
        default_value_var,
        input_fields_var,
    ):
        return group_config_ui.create_group_input_mapping_callbacks(
            self,
            config,
            transit_context,
            get_source_headers,
            mapping_tree,
            selected_input_combo,
            selected_input_var,
            source_field_combo,
            source_field_var,
            default_value_var,
            input_fields_var,
            messagebox_module=_window_messagebox(self),
        )

    def infer_and_apply_group_input_fields_for_config(
        self,
        config,
        transit_context,
        get_source_headers,
        set_input_fields_text,
        refresh_mapping,
    ):
        return group_config_ui.infer_and_apply_group_input_fields_for_config(
            self,
            config,
            transit_context,
            get_source_headers,
            set_input_fields_text,
            refresh_mapping,
            messagebox_module=_window_messagebox(self),
        )

    def build_group_inner_nodes_section(self, frame, config, row):
        return group_config_ui.build_group_inner_nodes_section(
            self,
            frame,
            config,
            row,
            messagebox_module=_window_messagebox(self),
        )

    def build_group_node_config(self, config, headers, transit_context=None):
        return group_config_ui.build_group_node_config(
            self,
            config,
            headers,
            transit_context=transit_context,
        )
