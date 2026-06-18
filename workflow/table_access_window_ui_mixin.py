# -*- coding: utf-8 -*-
"""Thin UI wrapper mixin for table-access window helpers."""

from workflow import table_access_audit_ui
from workflow import table_access_window_ui


class TableAccessWindowUiMixin:
    """Compatibility wrappers around split table-access UI modules."""

    def table_access_log_text(self, event):
        return table_access_audit_ui.table_access_log_text(event)

    def open_table_access_audit_window(self):
        return table_access_audit_ui.open_table_access_audit_window(self)

    def build_table_access_window_shell(self):
        return table_access_window_ui.build_table_access_window_shell(self)

    def build_table_access_list_section(self, parent):
        return table_access_window_ui.build_table_access_list_section(self, parent)

    def build_table_access_table_form_section(self, parent):
        return table_access_window_ui.build_table_access_table_form_section(self, parent)

    def build_table_access_field_form_section(self, parent):
        return table_access_window_ui.build_table_access_field_form_section(self, parent)

    def build_table_access_table_action_buttons(self, table_form, commands):
        return table_access_window_ui.build_table_access_table_action_buttons(self, table_form, commands)

    def build_table_access_field_action_buttons(self, field_form, commands):
        return table_access_window_ui.build_table_access_field_action_buttons(self, field_form, commands)

    def build_table_access_bottom_buttons(self, win, commands):
        return table_access_window_ui.build_table_access_bottom_buttons(self, win, commands)

    def current_table_access_window_node(self, state):
        return table_access_window_ui.current_table_access_window_node(self, state)

    def refresh_table_access_node_tree(self, node_tree, state):
        return table_access_window_ui.refresh_table_access_node_tree(self, node_tree, state)

    def load_table_access_table_form(self, table_section, entry, table_choices):
        return table_access_window_ui.load_table_access_table_form(self, table_section, entry, table_choices)

    def refresh_table_access_field_choices(self, field_section, choices):
        return table_access_window_ui.refresh_table_access_field_choices(self, field_section, choices)

    def refresh_table_access_field_tree(self, state, field_tree, entry, field_section, choices):
        return table_access_window_ui.refresh_table_access_field_tree(
            self,
            state,
            field_tree,
            entry,
            field_section,
            choices,
        )

    def current_table_access_window_access(self, state):
        return table_access_window_ui.current_table_access_window_access(self, state)

    def current_table_access_window_table_entry(self, state):
        return table_access_window_ui.current_table_access_window_table_entry(self, state)

    def load_table_access_window_table_form(self, state, table_section, entry):
        return table_access_window_ui.load_table_access_window_table_form(self, state, table_section, entry)

    def collect_table_access_window_table_form(self, table_section):
        return table_access_window_ui.collect_table_access_window_table_form(self, table_section)

    def refresh_table_access_window_field_tree(self, state, field_section, field_tree):
        return table_access_window_ui.refresh_table_access_window_field_tree(self, state, field_section, field_tree)

    def refresh_table_access_window_table_tree(
        self,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        select_index=None,
    ):
        return table_access_window_ui.refresh_table_access_window_table_tree(
            self,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            select_index=select_index,
        )

    def on_table_access_window_node_selected(
        self,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
        event=None,
        force=False,
    ):
        return table_access_window_ui.on_table_access_window_node_selected(
            self,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
            event=event,
            force=force,
        )

    def on_table_access_window_table_selected(
        self,
        state,
        table_section,
        field_section,
        table_tree,
        field_tree,
        event=None,
    ):
        return table_access_window_ui.on_table_access_window_table_selected(
            self,
            state,
            table_section,
            field_section,
            table_tree,
            field_tree,
            event=event,
        )

    def on_table_access_window_field_selected(self, state, field_section, field_tree, event=None):
        return table_access_window_ui.on_table_access_window_field_selected(
            self,
            state,
            field_section,
            field_tree,
            event=event,
        )

    def save_table_access_window_table_entry(
        self,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    ):
        return table_access_window_ui.save_table_access_window_table_entry(
            self,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def add_table_access_window_table_entry(
        self,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
    ):
        return table_access_window_ui.add_table_access_window_table_entry(
            self,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
        )

    def delete_table_access_window_table_entry(
        self,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    ):
        return table_access_window_ui.delete_table_access_window_table_entry(
            self,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def rebuild_table_access_window_default_access(
        self,
        win,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    ):
        return table_access_window_ui.rebuild_table_access_window_default_access(
            self,
            win,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def check_table_access_window_permissions(self, win, status_var):
        return table_access_window_ui.check_table_access_window_permissions(self, win, status_var)

    def preview_table_access_window_impact(self, win, state):
        return table_access_window_ui.preview_table_access_window_impact(self, win, state)

    def apply_table_access_window_table_preset(self, table_section, event=None):
        return table_access_window_ui.apply_table_access_window_table_preset(self, table_section, event=event)

    def save_table_access_window_field_entry(self, state, table_section, field_section, field_tree, status_var):
        return table_access_window_ui.save_table_access_window_field_entry(
            self,
            state,
            table_section,
            field_section,
            field_tree,
            status_var,
        )

    def add_table_access_window_field_entry(self, table_section, field_section, field_tree):
        return table_access_window_ui.add_table_access_window_field_entry(self, table_section, field_section, field_tree)

    def delete_table_access_window_field_entry(self, state, field_section, field_tree, status_var):
        return table_access_window_ui.delete_table_access_window_field_entry(
            self,
            state,
            field_section,
            field_tree,
            status_var,
        )

    def auto_match_table_access_window_fields(self, state, field_section, field_tree, status_var):
        return table_access_window_ui.auto_match_table_access_window_fields(
            self,
            state,
            field_section,
            field_tree,
            status_var,
        )

    def auto_match_table_access_window_fields_by_order(self, state, table_section, field_section, field_tree, status_var):
        return table_access_window_ui.auto_match_table_access_window_fields_by_order(
            self,
            state,
            table_section,
            field_section,
            field_tree,
            status_var,
        )

    def clear_table_access_window_fields(self, state, field_section, field_tree, status_var):
        return table_access_window_ui.clear_table_access_window_fields(self, state, field_section, field_tree, status_var)

    def create_table_access_selection_callbacks(
        self,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    ):
        return table_access_window_ui.create_table_access_selection_callbacks(
            self,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def create_table_access_table_action_callbacks(
        self,
        win,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    ):
        return table_access_window_ui.create_table_access_table_action_callbacks(
            self,
            win,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def create_table_access_field_action_callbacks(
        self,
        state,
        table_section,
        field_section,
        field_tree,
        status_var,
    ):
        return table_access_window_ui.create_table_access_field_action_callbacks(
            self,
            state,
            table_section,
            field_section,
            field_tree,
            status_var,
        )

    def create_table_access_window_callbacks(
        self,
        win,
        state,
        table_section,
        field_section,
        node_tree,
        table_tree,
        field_tree,
        status_var,
    ):
        return table_access_window_ui.create_table_access_window_callbacks(
            self,
            win,
            state,
            table_section,
            field_section,
            node_tree,
            table_tree,
            field_tree,
            status_var,
        )

    def open_table_access_window(self, initial_index=None):
        return table_access_window_ui.open_table_access_window(self, initial_index=initial_index)
