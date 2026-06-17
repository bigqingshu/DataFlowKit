# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for jump validation and manager wrappers."""

from workflow import jump_analysis as workflow_jump_analysis
from workflow import jump_manager_ui as workflow_jump_manager_ui


class WorkflowJumpMixin:
    """Compatibility methods used by jump validation and manager UI modules."""

    def jump_node_label(self, idx, node):
        return workflow_jump_analysis.jump_node_label(idx, node)

    def collect_jump_anchors(self, nodes=None):
        node_list = nodes if nodes is not None else self.nodes
        return workflow_jump_analysis.collect_jump_anchors(nodes=node_list)

    def collect_condition_flag_producers(self, nodes=None):
        node_list = nodes if nodes is not None else self.nodes
        return workflow_jump_analysis.collect_condition_flag_producers(nodes=node_list)

    def resolve_jump_anchor_index(self, anchor_id, anchors_info=None, nodes=None):
        node_list = nodes if nodes is not None else self.nodes
        return workflow_jump_analysis.resolve_jump_anchor_index(anchor_id, anchors_info=anchors_info, nodes=node_list)

    def jump_relation_status_text(self, relation, anchors_info=None, nodes=None):
        node_list = nodes if nodes is not None else self.nodes
        return workflow_jump_analysis.jump_relation_status_text(relation, anchors_info=anchors_info, nodes=node_list)

    def collect_jump_relations(self, nodes=None, anchors_info=None):
        node_list = nodes if nodes is not None else self.nodes
        return workflow_jump_analysis.collect_jump_relations(nodes=node_list, anchors_info=anchors_info)

    def add_jump_validation_issue(self, issues, severity, item, message, suggestion="", relation=None, anchor=None):
        return workflow_jump_analysis.add_jump_validation_issue(
            issues,
            severity,
            item,
            message,
            suggestion=suggestion,
            relation=relation,
            anchor=anchor,
        )

    def next_enabled_node_after_anchor(self, anchor, nodes=None):
        node_list = nodes if nodes is not None else self.nodes
        return workflow_jump_analysis.next_enabled_node_after_anchor(anchor, nodes=node_list)

    def validate_jump_relations(self, nodes=None):
        node_list = nodes if nodes is not None else self.nodes
        return workflow_jump_analysis.validate_jump_relations(nodes=node_list)

    def jump_validation_summary_text(self, issues):
        return workflow_jump_analysis.jump_validation_summary_text(issues)

    def jump_issue_detail_text(self, issue):
        return workflow_jump_analysis.jump_issue_detail_text(issue)

    def show_jump_precheck_dialog(self, issues, title="跳转校验", allow_continue=False):
        return workflow_jump_manager_ui.show_jump_precheck_dialog(
            self,
            issues,
            title=title,
            allow_continue=allow_continue,
        )

    def confirm_jump_precheck(self, execute_actions=False, stop_index=None):
        return workflow_jump_analysis.confirm_jump_precheck(
            self,
            execute_actions=execute_actions,
            stop_index=stop_index,
        )

    def open_jump_manager_window(self):
        return workflow_jump_manager_ui.open_jump_manager_window(self)
