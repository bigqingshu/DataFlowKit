# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for workflow execution wrappers."""

import copy
import os
import sys

from workflow import run_plan_context as workflow_run_plan_context
from workflow import run_plan_loop as workflow_run_plan_loop
from workflow.workflow_background_task_mixin import WorkflowBackgroundTaskMixin
from workflow.workflow_execute_plan_actions_mixin import WorkflowExecutePlanActionsMixin
from workflow.workflow_manual_loop_execution_mixin import WorkflowManualLoopExecutionMixin


def _get_app_dir(window):
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


class WorkflowExecutionMixin(
    WorkflowBackgroundTaskMixin,
    WorkflowManualLoopExecutionMixin,
    WorkflowExecutePlanActionsMixin,
):
    """Compatibility methods used by workflow execution and background tasks."""

    def run_plan(
        self,
        stop_index=None,
        raise_error=False,
        execute_actions=False,
        return_context=False,
        start_index=0,
        initial_headers=None,
        initial_rows=None,
        initial_context=None,
        suppress_jump_at_stop=False,
        progress_callback=None,
        cancel_event=None,
        workflow_snapshot=None,
    ):
        initial_state = workflow_run_plan_context.build_run_plan_initial_state(
            self,
            stop_index=stop_index,
            start_index=start_index,
            initial_headers=initial_headers,
            initial_rows=initial_rows,
            initial_context=initial_context,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
            workflow_snapshot=workflow_snapshot,
            normalize_policy=self.normalize_table_access_policy,
        )
        final_state = workflow_run_plan_loop.execute_run_plan_loop(
            self,
            initial_state,
            execute_actions=execute_actions,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
            suppress_jump_at_stop=suppress_jump_at_stop,
            raise_error=raise_error,
        )
        return workflow_run_plan_loop.build_run_plan_result(
            final_state["headers"],
            final_state["rows"],
            final_state["logs"],
            final_state["context"],
            return_context=return_context,
        )

    def build_workflow_task_snapshot(self, mode, stop_index=None, execute_actions=False):
        return {
            "mode": mode,
            "stop_index": stop_index,
            "execute_actions": bool(execute_actions),
            "app_dir": _get_app_dir(self),
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
