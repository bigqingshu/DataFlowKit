# -*- coding: utf-8 -*-
"""PlanWorkflowWindow mixin for manual loop-step execution."""

import sys

from tkinter import messagebox as tk_messagebox


def _window_messagebox(window):
    module = sys.modules.get(window.__class__.__module__)
    return getattr(module, "messagebox", tk_messagebox)


class WorkflowManualLoopExecutionMixin:
    """Compatibility methods for stepping through loop nodes from the config UI."""

    def reset_manual_loop_context(self):
        self.manual_loop_context = None
        self.manual_loop_headers = None
        self.manual_loop_rows = None
        self.manual_loop_start_idx = None
        self.manual_loop_judge_idx = None
        self.manual_loop_after_index = None
        self.manual_loop_logs = []
        self.status_var.set("已重置单步循环缓存。后续预览将重新从计划开头执行。")

    def _resolve_selected_loop_judge(self, msg):
        idx = self.get_selected_node_index()
        if idx is None:
            msg.showwarning("提示", "请先选择一个【循环判断回跳】节点。")
            return None
        node = self.nodes[idx]
        if node.get("type") != "循环判断回跳":
            msg.showwarning("提示", "请先选中【循环判断回跳】节点，再点击执行循环一次。")
            return None
        loop_id = node.get("config", {}).get("loop_id", "")
        if not loop_id:
            msg.showwarning("提示", "当前循环判断节点没有绑定循环名称。")
            return None
        start_idx = self.find_loop_start_index(loop_id, idx)
        if start_idx is None:
            msg.showerror("循环错误", f"未找到对应循环执行起点：{loop_id}")
            return None
        return idx, node, loop_id, start_idx

    def _manual_loop_cache_matches(self, start_idx, judge_idx):
        return (
            self.manual_loop_context is not None
            and self.manual_loop_start_idx == start_idx
            and self.manual_loop_judge_idx == judge_idx
        )

    def _initialize_manual_loop_context(self, start_idx, judge_idx):
        if start_idx > 0:
            base_headers, base_rows, base_logs, base_context = self.run_plan(
                stop_index=start_idx - 1,
                raise_error=True,
                return_context=True,
            )
        else:
            base_headers = list(self.app.headers)
            base_rows = [list(r) for r in self.app.rows]
            base_logs = []
            base_context = {"transit_tables": {}, "loop_states": {}, "loop_results": {}}
        self.manual_loop_headers = base_headers
        self.manual_loop_rows = base_rows
        self.manual_loop_context = base_context
        self.manual_loop_start_idx = start_idx
        self.manual_loop_judge_idx = judge_idx
        self.manual_loop_after_index = judge_idx + 1
        self.manual_loop_logs = list(base_logs)

    def _run_manual_loop_once(self, start_idx, judge_idx):
        headers, rows, logs, context = self.run_plan(
            start_index=start_idx,
            stop_index=judge_idx,
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
        return headers, rows, logs, context

    def _manual_loop_display_table(self, node, headers, rows):
        result_name = node.get("config", {}).get("result_table_name", "循环结果") or "循环结果"
        if result_name not in self.current_transit_tables:
            return headers, rows
        item = self.current_transit_tables[result_name]
        return list(item.get("headers", headers)), [list(r) for r in item.get("rows", rows)]

    def _set_manual_loop_preview_and_status(self, node, loop_id, headers, rows, logs, context):
        display_headers, display_rows = self._manual_loop_display_table(node, headers, rows)
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

    def execute_loop_once_from_selected_judge(self):
        msg = _window_messagebox(self)
        selected = self._resolve_selected_loop_judge(msg)
        if selected is None:
            return
        idx, node, loop_id, start_idx = selected
        try:
            if not self._manual_loop_cache_matches(start_idx, idx):
                self._initialize_manual_loop_context(start_idx, idx)
            headers, rows, logs, context = self._run_manual_loop_once(start_idx, idx)
            self._set_manual_loop_preview_and_status(node, loop_id, headers, rows, logs, context)
        except Exception as e:
            msg.showerror("执行循环一次失败", str(e))
