# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for workflow task snapshots."""

import copy
import os
import sys

from workflow.protocol_adapter import build_workflow_plan_payload


def get_workflow_task_app_dir(window):
    app = getattr(window, "app", None)
    app_dir = getattr(app, "app_dir", None) if app is not None else None
    if app_dir:
        return app_dir
    app_dir = getattr(window, "app_dir", None)
    if app_dir:
        return app_dir
    module = sys.modules.get(window.__class__.__module__)
    get_app_dir = getattr(module, "get_app_dir", None) if module is not None else None
    if callable(get_app_dir):
        return get_app_dir()
    return os.getcwd()


class WorkflowTaskSnapshotMixin:
    """Compatibility methods for capturing workflow state before background execution."""

    def build_workflow_protocol_plan(self, plan_name=None, include_input=False):
        plan_name = str(plan_name or "").strip() or self.output_table_var.get().strip() or "工作流计划"
        headers = copy.deepcopy(self.app.headers) if include_input else None
        rows = copy.deepcopy(self.app.rows) if include_input else None
        return build_workflow_plan_payload(
            plan_name=plan_name,
            nodes=self.nodes,
            output_mode=self.output_mode_var.get(),
            output_table=self.output_table_var.get().strip(),
            backup_before_overwrite=bool(self.backup_before_overwrite_var.get()),
            table_access_policy=self.normalize_table_access_policy(),
            headers=headers,
            rows=rows,
            metadata={"client": "tkinter"},
            ensure_node_id=self.ensure_node_identity,
        )

    def build_workflow_task_snapshot(self, mode, stop_index=None, execute_actions=False):
        snapshot = {
            "mode": mode,
            "stop_index": stop_index,
            "execute_actions": bool(execute_actions),
            "app_dir": get_workflow_task_app_dir(self),
            "db_path": self.app.db_path_var.get().strip(),
            "workflow_name": self.output_table_var.get().strip(),
            "output_table": self.output_table_var.get().strip(),
            "output_mode": self.output_mode_var.get(),
            "backup_before_overwrite": bool(self.backup_before_overwrite_var.get()),
            "table_access_policy": self.normalize_table_access_policy(),
            "headers": copy.deepcopy(self.app.headers),
            "rows": copy.deepcopy(self.app.rows),
            "nodes": copy.deepcopy(self.nodes),
            "manual_loop_context": copy.deepcopy(self.manual_loop_context) if self.manual_loop_context is not None else None,
            "manual_loop_after_index": self.manual_loop_after_index,
            "manual_loop_headers": copy.deepcopy(self.manual_loop_headers) if self.manual_loop_headers is not None else None,
            "manual_loop_rows": copy.deepcopy(self.manual_loop_rows) if self.manual_loop_rows is not None else None,
        }
        snapshot["workflow_plan"] = self.build_workflow_protocol_plan(
            plan_name=snapshot["workflow_name"],
            include_input=True,
        )
        return snapshot
