# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for workflow execution wrappers."""

import copy
import os
import sys

from tkinter import messagebox as tk_messagebox

from workflow import background_workflow as workflow_background_workflow
from workflow import run_plan_context as workflow_run_plan_context
from workflow import run_plan_loop as workflow_run_plan_loop


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


class WorkflowExecutionMixin:
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

    def start_workflow_task(self, task_type, title=None, stop_index=None, execute_actions=False):
        title = title or task_type
        return self._start_background_workflow(task_type, title, stop_index=stop_index, execute_actions=execute_actions)

    def _iter_workflow_child_widgets(self, parent):
        for child in parent.winfo_children():
            yield child
            yield from self._iter_workflow_child_widgets(child)

    def _set_workflow_cancel_enabled(self, enabled):
        try:
            if self.workflow_cancel_button is not None and self.workflow_cancel_button.winfo_exists():
                self.workflow_cancel_button.configure(state="normal" if enabled else "disabled")
        except Exception:
            pass

    def _set_workflow_controls_enabled(self, enabled):
        classes = {"TButton", "TCombobox", "TEntry", "TCheckbutton", "TRadiobutton", "Entry", "Text", "Listbox", "Button", "Checkbutton", "Radiobutton", "Spinbox", "TSpinbox"}
        if not enabled:
            self.workflow_widget_state_backup = {}
            for widget in self._iter_workflow_child_widgets(self.window):
                if widget is self.workflow_cancel_button:
                    continue
                try:
                    if widget.winfo_class() not in classes:
                        continue
                    old_state = widget.cget("state")
                    self.workflow_widget_state_backup[widget] = old_state
                    widget.configure(state="disabled")
                except Exception:
                    continue
            self._set_workflow_cancel_enabled(True)
            return
        for widget, old_state in list(self.workflow_widget_state_backup.items()):
            try:
                if widget.winfo_exists():
                    widget.configure(state=old_state)
            except Exception:
                pass
        self.workflow_widget_state_backup = {}
        self._set_workflow_cancel_enabled(False)

    def is_background_workflow_running(self):
        return bool(self.workflow_worker_running and self.workflow_worker_thread and self.workflow_worker_thread.is_alive())

    def cancel_background_workflow(self):
        if not self.is_background_workflow_running():
            self.worker_status_text.set("执行状态：当前没有后台任务。")
            return
        if self.workflow_worker_cancel is not None:
            self.workflow_worker_cancel.set()
        self.worker_status_text.set("执行状态：正在请求取消，当前节点会在安全检查点停止。")

    def _set_background_workflow_state(self, running, title=""):
        self.workflow_worker_running = bool(running)
        if running:
            self.workflow_current_task = title
            self._set_workflow_controls_enabled(False)
            self.worker_status_text.set(f"执行状态：后台运行中 - {title}")
            self.workflow_progress_var.set(0)
            self.node_progress_var.set(0)
            self.workflow_progress_text.set("总进度：准备开始")
            self.node_progress_text.set("当前节点：等待执行")
        else:
            self.workflow_worker_running = False
            self.workflow_current_task = None
            self._set_workflow_controls_enabled(True)

    def _start_background_workflow(self, mode, title, stop_index=None, execute_actions=False):
        return workflow_background_workflow.start_background_workflow(
            self,
            mode,
            title,
            stop_index=stop_index,
            execute_actions=execute_actions,
        )

    def _background_progress_callback(self, message):
        try:
            self.workflow_worker_queue.put(message)
        except Exception:
            pass

    def _background_workflow_worker(self, mode, stop_index=None, execute_actions=False, snapshot=None):
        return workflow_background_workflow.background_workflow_worker(
            self,
            mode,
            stop_index=stop_index,
            execute_actions=execute_actions,
            snapshot=snapshot,
        )

    def _poll_background_workflow_queue(self):
        return workflow_background_workflow.poll_background_workflow_queue(self)

    def _handle_background_workflow_message(self, msg):
        return workflow_background_workflow.handle_background_workflow_message(self, msg)

    def _finish_execute_plan_output(self, headers, rows, logs, context=None, snapshot=None):
        return workflow_background_workflow.finish_execute_plan_output(
            self,
            headers,
            rows,
            logs,
            context=context,
            snapshot=snapshot,
        )

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

    def reset_manual_loop_context(self):
        self.manual_loop_context = None
        self.manual_loop_headers = None
        self.manual_loop_rows = None
        self.manual_loop_start_idx = None
        self.manual_loop_judge_idx = None
        self.manual_loop_after_index = None
        self.manual_loop_logs = []
        self.status_var.set("已重置单步循环缓存。后续预览将重新从计划开头执行。")

    def execute_loop_once_from_selected_judge(self):
        msg = _window_messagebox(self)
        idx = self.get_selected_node_index()
        if idx is None:
            msg.showwarning("提示", "请先选择一个【循环判断回跳】节点。")
            return
        node = self.nodes[idx]
        if node.get("type") != "循环判断回跳":
            msg.showwarning("提示", "请先选中【循环判断回跳】节点，再点击执行循环一次。")
            return
        loop_id = node.get("config", {}).get("loop_id", "")
        if not loop_id:
            msg.showwarning("提示", "当前循环判断节点没有绑定循环名称。")
            return
        start_idx = self.find_loop_start_index(loop_id, idx)
        if start_idx is None:
            msg.showerror("循环错误", f"未找到对应循环执行起点：{loop_id}")
            return
        try:
            if (self.manual_loop_context is None or
                self.manual_loop_start_idx != start_idx or
                self.manual_loop_judge_idx != idx):
                if start_idx > 0:
                    base_headers, base_rows, base_logs, base_context = self.run_plan(stop_index=start_idx - 1, raise_error=True, return_context=True)
                else:
                    base_headers = list(self.app.headers)
                    base_rows = [list(r) for r in self.app.rows]
                    base_logs = []
                    base_context = {"transit_tables": {}, "loop_states": {}, "loop_results": {}}
                self.manual_loop_headers = base_headers
                self.manual_loop_rows = base_rows
                self.manual_loop_context = base_context
                self.manual_loop_start_idx = start_idx
                self.manual_loop_judge_idx = idx
                self.manual_loop_after_index = idx + 1
                self.manual_loop_logs = list(base_logs)

            headers, rows, logs, context = self.run_plan(
                start_index=start_idx,
                stop_index=idx,
                raise_error=True,
                return_context=True,
                initial_headers=self.manual_loop_headers,
                initial_rows=self.manual_loop_rows,
                initial_context=self.manual_loop_context,
                suppress_jump_at_stop=True,
            )
            self.manual_loop_headers = headers
            self.manual_loop_rows = rows
            self.manual_loop_context = context
            self.manual_loop_logs.extend(logs)
            self.current_transit_tables = context.get("transit_tables", {})

            result_name = node.get("config", {}).get("result_table_name", "循环结果") or "循环结果"
            display_headers, display_rows = headers, rows
            if result_name in self.current_transit_tables:
                item = self.current_transit_tables[result_name]
                display_headers = list(item.get("headers", headers))
                display_rows = [list(r) for r in item.get("rows", rows)]

            self.set_plan_preview_result(display_headers, display_rows, display=True)

            state = context.get("loop_states", {}).get(loop_id, {})
            done = sum(1 for r in state.get("queue_rows", []) if str(r[0]).strip() == "2")
            pending = sum(1 for r in state.get("queue_rows", []) if str(r[0]).strip() == "0")
            failed = sum(1 for r in state.get("queue_rows", []) if str(r[0]).strip() == "3")
            self.status_var.set(
                f"已执行循环一次：{loop_id}，完成 {done}，待执行 {pending}，失败 {failed}。"
                f"后续选择判断节点之后的节点预览时，会基于当前单步循环缓存继续执行。"
                + self.format_logs(logs)
            )
        except Exception as e:
            msg.showerror("执行循环一次失败", str(e))
