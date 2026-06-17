# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for preview and execute-plan UI actions."""

import sys

from tkinter import messagebox as tk_messagebox


def _window_messagebox(window):
    module = sys.modules.get(window.__class__.__module__)
    return getattr(module, "messagebox", tk_messagebox)


class WorkflowExecutePlanActionsMixin:
    """Compatibility methods for workflow preview and execute buttons."""

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
