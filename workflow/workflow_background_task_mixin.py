# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for background workflow task state and wrappers."""

from workflow import background_workflow as workflow_background_workflow


class WorkflowBackgroundTaskMixin:
    """Compatibility methods used by background workflow services and UI controls."""

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
