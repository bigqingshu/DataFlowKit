# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for workflow execution wrappers."""

from workflow import run_plan_context as workflow_run_plan_context
from workflow import run_plan_loop as workflow_run_plan_loop
from workflow.workflow_background_task_mixin import WorkflowBackgroundTaskMixin
from workflow.workflow_execute_plan_actions_mixin import WorkflowExecutePlanActionsMixin
from workflow.workflow_manual_loop_execution_mixin import WorkflowManualLoopExecutionMixin
from workflow.workflow_task_snapshot_mixin import WorkflowTaskSnapshotMixin


class WorkflowExecutionMixin(
    WorkflowBackgroundTaskMixin,
    WorkflowManualLoopExecutionMixin,
    WorkflowExecutePlanActionsMixin,
    WorkflowTaskSnapshotMixin,
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
