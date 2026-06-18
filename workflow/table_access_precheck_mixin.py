# -*- coding: utf-8 -*-
"""Table-access precheck wrappers for PlanWorkflowWindow."""

import os

from db import TableAccessManager
from workflow import plan_workflow_ui
from workflow.table_access_precheck import (
    evaluate_node_table_access_precheck,
    evaluate_workflow_output_precheck,
    find_matching_table_access_entry as workflow_find_matching_table_access_entry,
    iter_nodes_for_table_access_precheck,
    make_table_access_precheck_issue as workflow_make_table_access_precheck_issue,
    normalize_precheck_transit_name as workflow_normalize_precheck_transit_name,
    table_access_entry_match_score as workflow_table_access_entry_match_score,
    table_access_precheck_actionable as workflow_table_access_precheck_actionable,
    table_access_precheck_blocking as workflow_table_access_precheck_blocking,
    table_access_precheck_summary_text as workflow_table_access_precheck_summary_text,
    table_access_precheck_sort_key,
)


class TableAccessPrecheckMixin:
    """Compatibility wrappers around table-access precheck helpers."""

    def table_access_entry_match_score(self, actual, expected):
        return workflow_table_access_entry_match_score(actual, expected)

    def find_matching_table_access_entry(self, actual_tables, expected):
        return workflow_find_matching_table_access_entry(actual_tables, expected)

    def normalize_precheck_transit_name(self, table_name):
        return workflow_normalize_precheck_transit_name(table_name)

    def add_table_access_precheck_issue(self, issues, severity, node_label, node, entry, message,
                                        suggestion="", category="permission", blocking=None):
        issues.append(workflow_make_table_access_precheck_issue(
            severity,
            node_label,
            node,
            entry,
            message,
            suggestion=suggestion,
            category=category,
            blocking=blocking,
            write_mode_formatter=self.write_mode_display_text,
        ))

    def table_access_precheck_summary_text(self, issues):
        return workflow_table_access_precheck_summary_text(issues)

    def table_access_precheck_actionable(self, issues):
        return workflow_table_access_precheck_actionable(issues)

    def table_access_precheck_blocking(self, issues):
        return workflow_table_access_precheck_blocking(issues)

    def get_precheck_sqlite_tables(self):
        db_path = self.get_workflow_db_path()
        if not db_path or not os.path.exists(db_path):
            return None
        try:
            return set(TableAccessManager(db_path, node_type="权限预检").list_tables())
        except Exception:
            return None

    def confirm_table_access_precheck(self, execute_actions=True, stop_index=None):
        issues = self.build_table_access_precheck(execute_actions=execute_actions, stop_index=stop_index)
        self.last_table_access_precheck = list(issues or [])
        actionable = self.table_access_precheck_actionable(issues)
        if not actionable:
            self.status_var.set(self.table_access_precheck_summary_text(issues))
            return True
        policy = self.normalize_table_access_policy()
        if policy == "audit":
            self.status_var.set(self.table_access_precheck_summary_text(actionable) + " 当前策略为只审计，执行不会因预检提示而中断。")
            return True
        if policy == "strict":
            blocking = self.table_access_precheck_blocking(actionable)
            if not blocking:
                self.status_var.set(self.table_access_precheck_summary_text(actionable) + " 当前仅有风险提醒，强制模式允许继续执行。")
                return True
            self.show_table_access_precheck_dialog(
                blocking,
                title="执行前权限预检 - 强制拦截",
                allow_continue=False,
            )
            self.status_var.set("执行计划已拦截：当前权限策略为强制拦截，请先处理权限预检项。")
            return False
        return self.show_table_access_precheck_dialog(
            actionable,
            title="执行前权限预检",
            allow_continue=True,
        )

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
