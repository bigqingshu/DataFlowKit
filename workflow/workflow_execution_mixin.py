# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for workflow execution wrappers."""

import copy
import os
import sys

from tkinter import messagebox as tk_messagebox

from workflow import run_plan_context as workflow_run_plan_context
from workflow import run_plan_loop as workflow_run_plan_loop
from workflow.workflow_background_task_mixin import WorkflowBackgroundTaskMixin
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


def _window_messagebox(window):
    module = sys.modules.get(window.__class__.__module__)
    return getattr(module, "messagebox", tk_messagebox)


class WorkflowExecutionMixin(WorkflowBackgroundTaskMixin, WorkflowManualLoopExecutionMixin):
    """Compatibility methods used by workflow execution and background tasks."""

    def _has_actual_rename_node(self):
        return any(
            node.get("enabled", True) and node.get("type") == "批量重命名" and node.get("config", {}).get("actual_rename")
            for node in self.nodes
        )

    def _should_prompt_execute_plan_preview_reuse(self):
        return bool(self.preview_dirty and self.preview_headers and self.preview_rows and not self._has_actual_rename_node())

    def _finish_execute_plan_from_preview(self):
        self._finish_execute_plan_output(
            list(self.preview_headers),
            [list(row) for row in self.preview_rows],
            ["使用手动修改后的当前计划预览结果输出"],
            snapshot=self.build_workflow_task_snapshot("execute_plan", execute_actions=True),
        )

    def _confirm_execute_plan_preview_reuse(self, msg):
        if not self._should_prompt_execute_plan_preview_reuse():
            return False
        use_current_preview = msg.askyesno(
            "使用已修改的计划预览？",
            "检测到结果预览区存在手动修改。\n\n"
            "选择【是】：使用当前预览数据作为输出，不重新执行计划。\n"
            "选择【否】：重新执行计划，当前预览修改会被覆盖。"
        )
        if not use_current_preview:
            return False
        self._finish_execute_plan_from_preview()
        return True

    def _confirm_execute_plan_actual_rename(self, msg):
        if not self._has_actual_rename_node():
            return True
        ok = msg.askyesno(
            "确认执行批量重命名",
            "当前计划中存在已勾选【实际执行重命名】的节点。\n\n"
            "执行后会修改磁盘上的文件/文件夹名称。建议先使用【预览完整计划】确认结果无误。\n\n是否继续执行？"
        )
        return bool(ok)

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

    def preview_to_selected_node(self):
        idx = self.get_selected_node_index()
        if idx is None:
            _window_messagebox(self).showwarning("提示", "请先选择一个节点。")
            return
        self.start_workflow_task("preview_to", f"预览到节点 {idx + 1}", stop_index=idx, execute_actions=False)

    def preview_full_plan(self):
        self.start_workflow_task("preview_full", "预览完整计划", stop_index=None, execute_actions=False)

    def execute_plan(self):
        msg = _window_messagebox(self)
        if self.is_background_workflow_running():
            msg.showwarning("后台任务运行中", "当前已有工作流正在后台执行。")
            return
        if self._confirm_execute_plan_preview_reuse(msg):
            return
        if not self._confirm_execute_plan_actual_rename(msg):
            return
        self.start_workflow_task("execute_plan", "执行计划", stop_index=None, execute_actions=True)
