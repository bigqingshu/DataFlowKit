# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for table-access window wrappers."""

import os

from workflow import plan_workflow_ui
from workflow import table_access_audit_ui
from workflow import table_access_window_ui
from workflow.table_access_precheck import (
    evaluate_node_table_access_precheck,
    evaluate_workflow_output_precheck,
    iter_nodes_for_table_access_precheck,
    table_access_precheck_sort_key,
)


class TableAccessWindowMixin:
    """Compatibility methods used by table-access UI modules."""

    def show_table_access_precheck_dialog(self, issues, title="权限预检", allow_continue=False):
        return plan_workflow_ui.show_table_access_precheck_dialog(
            self,
            issues,
            title=title,
            allow_continue=allow_continue,
        )

    def open_table_access_precheck_window(self):
        issues = self.build_table_access_precheck(execute_actions=True)
        self.show_table_access_precheck_dialog(issues, title="权限预检", allow_continue=False)

    def table_access_precheck_sort_key(self, issue):
        return table_access_precheck_sort_key(issue)

    def iter_nodes_for_table_access_precheck(self, nodes=None, stop_index=None, prefix=""):
        node_list = nodes if nodes is not None else self.nodes
        yield from iter_nodes_for_table_access_precheck(node_list, stop_index=stop_index, prefix=prefix)

    def build_table_access_precheck(self, execute_actions=True, stop_index=None, nodes=None):
        """Build table-access precheck issues from the current workflow configuration."""
        node_list = nodes if nodes is not None else self.nodes
        self.ensure_node_tree_identity(node_list)
        self.refresh_node_tree_table_access(node_list)

        issues = []
        db_path = self.get_workflow_db_path()
        sqlite_tables = self.get_precheck_sqlite_tables()
        produced_transit = set((self.current_transit_tables or {}).keys())
        permission_label_map = dict(self.table_access_permission_items())
        db_exists = os.path.exists(db_path) if db_path else None

        if execute_actions:
            output_mode = self.output_mode_var.get()
            output_table = self.output_table_var.get().strip()
            issues.extend(
                evaluate_workflow_output_precheck(
                    output_mode,
                    output_table,
                    db_path=db_path,
                    write_mode_formatter=self.write_mode_display_text,
                )
            )

        for node_label, node in self.iter_nodes_for_table_access_precheck(node_list, stop_index=stop_index):
            if not isinstance(node, dict):
                continue
            if not node.get("enabled", True):
                continue

            node_type = node.get("type", "")
            config = node.get("config", {}) or {}
            expected_access = self.default_table_access_for_node(node)
            actual_access = self.get_node_table_access(node)
            node_result = evaluate_node_table_access_precheck(
                node_label,
                node,
                expected_access,
                actual_access,
                permission_label_map=permission_label_map,
                execute_actions=execute_actions,
                db_path=db_path,
                db_exists=db_exists,
                sqlite_tables=sqlite_tables,
                produced_transit=produced_transit,
                needs_plugin_declaration=node_type == "插件节点" and self.plugin_needs_table_access_declaration(config),
                has_plugin_declaration=node_type == "插件节点" and self.plugin_has_table_access_declaration(config),
                write_mode_formatter=self.write_mode_display_text,
            )
            issues.extend(node_result.get("issues", []))
            for transit_name in node_result.get("produced_transit", []) or []:
                produced_transit.add(transit_name)

        issues.sort(key=self.table_access_precheck_sort_key)
        self.last_table_access_precheck = issues
        return issues

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
