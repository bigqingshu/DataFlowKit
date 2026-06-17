# -*- coding: utf-8 -*-
"""Background workflow worker and UI message helpers."""

import copy
import traceback
from tkinter import filedialog, messagebox


def background_workflow_worker(window, mode, stop_index=None, execute_actions=False, snapshot=None):
    logs = []
    snapshot = snapshot or {}
    try:
        window.workflow_worker_queue.put({"type": "workflow_start", "message": mode})
        if mode == "preview_to":
            idx = int(stop_index)
            manual_loop_context = snapshot.get("manual_loop_context")
            manual_loop_after_index = snapshot.get("manual_loop_after_index")
            if manual_loop_context is not None and manual_loop_after_index is not None and idx >= manual_loop_after_index:
                preview_context = copy.deepcopy(manual_loop_context)
                preview_context["allow_selected_columns_write_in_preview"] = True
                headers, rows, logs, context = window.run_plan(
                    start_index=manual_loop_after_index,
                    stop_index=idx,
                    raise_error=True,
                    return_context=True,
                    initial_headers=snapshot.get("manual_loop_headers"),
                    initial_rows=snapshot.get("manual_loop_rows"),
                    initial_context=preview_context,
                    progress_callback=window._background_progress_callback,
                    cancel_event=window.workflow_worker_cancel,
                    workflow_snapshot=snapshot,
                )
                prefix = f"已基于单步循环缓存预览到节点 {idx + 1}"
            else:
                preview_context = {"transit_tables": {}, "loop_states": {}, "loop_results": {}, "allow_selected_columns_write_in_preview": True}
                headers, rows, logs, context = window.run_plan(
                    stop_index=idx,
                    raise_error=True,
                    return_context=True,
                    initial_context=preview_context,
                    progress_callback=window._background_progress_callback,
                    cancel_event=window.workflow_worker_cancel,
                    workflow_snapshot=snapshot,
                )
                prefix = f"已预览到节点 {idx + 1}"
        elif mode == "preview_full":
            manual_loop_context = snapshot.get("manual_loop_context")
            manual_loop_after_index = snapshot.get("manual_loop_after_index")
            if manual_loop_context is not None and manual_loop_after_index is not None:
                preview_context = copy.deepcopy(manual_loop_context)
                preview_context["allow_selected_columns_write_in_preview"] = True
                headers, rows, logs, context = window.run_plan(
                    start_index=manual_loop_after_index,
                    stop_index=None,
                    raise_error=True,
                    return_context=True,
                    initial_headers=snapshot.get("manual_loop_headers"),
                    initial_rows=snapshot.get("manual_loop_rows"),
                    initial_context=preview_context,
                    progress_callback=window._background_progress_callback,
                    cancel_event=window.workflow_worker_cancel,
                    workflow_snapshot=snapshot,
                )
                prefix = "已基于单步循环缓存完成后续计划预览"
            else:
                preview_context = {"transit_tables": {}, "loop_states": {}, "loop_results": {}, "allow_selected_columns_write_in_preview": True}
                headers, rows, logs, context = window.run_plan(
                    stop_index=None,
                    raise_error=True,
                    return_context=True,
                    initial_context=preview_context,
                    progress_callback=window._background_progress_callback,
                    cancel_event=window.workflow_worker_cancel,
                    workflow_snapshot=snapshot,
                )
                prefix = "完整计划预览完成"
        elif mode == "execute_plan":
            headers, rows, logs, context = window.run_plan(
                stop_index=None,
                raise_error=True,
                execute_actions=execute_actions,
                return_context=True,
                progress_callback=window._background_progress_callback,
                cancel_event=window.workflow_worker_cancel,
                workflow_snapshot=snapshot,
            )
            prefix = "计划执行完成"
        else:
            raise ValueError(f"未知后台任务模式：{mode}")

        if window.workflow_worker_cancel is not None and window.workflow_worker_cancel.is_set():
            window.workflow_worker_queue.put({"type": "workflow_cancelled", "logs": logs})
            return
        window.workflow_worker_queue.put({
            "type": "workflow_done",
            "mode": mode,
            "prefix": prefix,
            "headers": headers,
            "rows": rows,
            "logs": logs,
            "context": context,
            "snapshot": snapshot,
        })
    except Exception as e:
        if window.workflow_worker_cancel is not None and window.workflow_worker_cancel.is_set():
            logs.append(f"用户取消后台任务：{e}")
            window.workflow_worker_queue.put({"type": "workflow_cancelled", "logs": logs})
            return
        tb = traceback.format_exc()
        log_path = window.write_workflow_error_log(mode, str(e), tb, logs=logs, snapshot=snapshot)
        window.workflow_worker_queue.put({
            "type": "workflow_error",
            "message": str(e),
            "traceback": tb,
            "log_path": log_path,
        })


def handle_background_workflow_message(window, msg):
    mtype = msg.get("type")
    if mtype == "workflow_start":
        window.workflow_progress_var.set(0)
        window.node_progress_var.set(0)
        window.workflow_progress_text.set("总进度：已启动后台执行")
        window.node_progress_text.set("当前节点：等待执行")
        return
    if mtype == "node_start":
        idx = int(msg.get("node_index", 0))
        total = max(1, int(msg.get("node_total", len(window.nodes) or 1)))
        percent = max(0, min(100, idx / total * 100))
        window.workflow_progress_var.set(percent)
        window.node_progress_var.set(0)
        window.workflow_progress_text.set(f"总进度：节点 {idx + 1} / {total}")
        window.node_progress_text.set(f"当前节点：{msg.get('node_name', '')} - 开始")
        window.worker_status_text.set(msg.get("message", "节点开始"))
        return
    if mtype == "node_progress":
        current = msg.get("current")
        total = msg.get("total")
        node_name = msg.get("node_name", "")
        message = msg.get("message", "节点处理中")
        detail_message = msg.get("detail_message") or msg.get("detail") or message
        try:
            current_f = float(current)
            total_f = float(total)
            if total_f > 0:
                percent = max(0, min(100, current_f / total_f * 100))
                window.node_progress_var.set(percent)
                if int(total_f) == total_f and int(current_f) == current_f:
                    window.node_progress_text.set(f"当前节点：{node_name} - {int(current_f)} / {int(total_f)}")
                else:
                    window.node_progress_text.set(f"当前节点：{node_name} - {current_f:g} / {total_f:g}")
            else:
                window.node_progress_text.set(f"当前节点：{node_name} - 处理中")
        except Exception:
            window.node_progress_text.set(f"当前节点：{node_name} - 处理中")
        window.worker_status_text.set(detail_message)
        return
    if mtype == "node_done":
        idx = int(msg.get("node_index", 0))
        total = max(1, int(msg.get("node_total", len(window.nodes) or 1)))
        percent = max(0, min(100, (idx + 1) / total * 100))
        window.workflow_progress_var.set(percent)
        window.node_progress_var.set(100)
        window.workflow_progress_text.set(f"总进度：节点 {idx + 1} / {total}")
        window.node_progress_text.set(f"当前节点：{msg.get('node_name', '')} - 完成，{msg.get('rows', 0)} 行 × {msg.get('cols', 0)} 列")
        window.worker_status_text.set(msg.get("message", "节点完成"))
        return
    if mtype == "node_error":
        window.node_progress_text.set(f"当前节点错误：{msg.get('node_name', '')}")
        window.worker_status_text.set(msg.get("message", "节点执行失败"))
        return
    if mtype == "workflow_cancelled":
        window._set_background_workflow_state(False)
        window.workflow_progress_text.set("总进度：已取消")
        window.node_progress_text.set("当前节点：已停止")
        window.status_var.set("后台工作流已取消。" + window.format_logs(msg.get("logs", [])))
        return
    if mtype == "workflow_error":
        window._set_background_workflow_state(False)
        window.workflow_progress_text.set("总进度：执行失败")
        window.node_progress_text.set("当前节点：失败")
        log_path = msg.get("log_path", "")
        if log_path:
            window.worker_status_text.set(f"执行状态：失败，错误日志：{log_path}")
            window.status_var.set(f"后台执行失败：{msg.get('message', '未知错误')}；错误日志：{log_path}")
        else:
            window.worker_status_text.set("执行状态：失败")
            window.status_var.set(f"后台执行失败：{msg.get('message', '未知错误')}")
        messagebox.showerror("后台执行失败", msg.get("message", "未知错误") + (f"\n\n错误日志：{log_path}" if log_path else ""))
        return
    if mtype == "workflow_done":
        window._set_background_workflow_state(False)
        headers = msg.get("headers", [])
        rows = msg.get("rows", [])
        logs = msg.get("logs", [])
        context = msg.get("context", {}) or {}
        snapshot = msg.get("snapshot") or context.get("workflow_snapshot", {}) or {}
        window.current_transit_tables = context.get("transit_tables", {})
        window.last_workflow_context = context
        window.last_table_access_logs = list(context.get("table_access_logs", []) or [])
        refresh_requests = context.get("ui_refresh_requests", []) or []
        if context.get("needs_refresh_table_list") or "table_list" in refresh_requests:
            try:
                window.app.refresh_table_list()
            except Exception:
                pass
        window.workflow_progress_var.set(100)
        window.node_progress_var.set(100)
        window.workflow_progress_text.set("总进度：完成")
        window.node_progress_text.set("当前节点：完成")
        mode = msg.get("mode")
        if mode in ("preview_full", "preview_to"):
            window.set_plan_preview_result(headers, rows, display=True)
            window.status_var.set(f"{msg.get('prefix', '预览完成')}：{len(rows)} 行 × {len(headers)} 列。" + window.format_logs(logs))
        elif mode == "execute_plan":
            window._finish_execute_plan_output(headers, rows, logs, context=context, snapshot=snapshot)
        return


def finish_execute_plan_output(window, headers, rows, logs, context=None, snapshot=None):
    context = context or {}
    snapshot_context = {"workflow_snapshot": snapshot or context.get("workflow_snapshot", {}) or {}}
    mode = window.get_workflow_output_mode(snapshot_context)
    if mode == "输出到主界面预览区":
        window.app.headers = list(headers)
        window.app.rows = [list(row) for row in rows]
        window.app.raw_data = ""
        window.app.refresh_tree()
        window.set_plan_preview_result(headers, rows, display=True)
        window.app.info_var.set(f"计划执行完成，已输出到主界面：{len(rows)} 行 × {len(headers)} 列。")
        window.status_var.set("计划执行完成，已输出到主界面。" + window.format_logs(logs))
        return

    if mode in ["保存为SQLite新表", "覆盖当前表"]:
        table_name = window.get_workflow_output_table(snapshot_context)
        if not table_name:
            messagebox.showwarning("提示", "请填写输出表名。")
            return
        overwrite = mode == "覆盖当前表"
        if overwrite:
            ok = messagebox.askyesno("确认覆盖", f"即将覆盖 SQLite 表：{table_name}\n覆盖前会按设置自动备份。是否继续？")
            if not ok:
                return
        try:
            saved_name = window.save_result_to_sqlite(
                headers,
                rows,
                table_name,
                overwrite=overwrite,
                backup=window.get_workflow_backup_before_overwrite(snapshot_context),
                context=context,
            )
            window.last_table_access_logs = list(context.get("table_access_logs", []) or [])
            window.app.refresh_table_list()
            window.status_var.set(f"计划执行完成，已保存到 SQLite 表：{saved_name}。" + window.format_logs(logs))
            messagebox.showinfo("保存成功", f"已保存计划结果。\n\n表名：{saved_name}\n行数：{len(rows)}\n列数：{len(headers)}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
        return

    if mode == "导出为xlsx":
        path = filedialog.asksaveasfilename(
            title="导出计划结果为 xlsx",
            defaultextension=".xlsx",
            filetypes=[("Excel文件", "*.xlsx"), ("所有文件", "*.*")]
        )
        if not path:
            return
        try:
            window.export_result_to_xlsx(headers, rows, path)
            window.status_var.set(f"计划执行完成，已导出：{path}。" + window.format_logs(logs))
            messagebox.showinfo("导出成功", f"已导出计划结果：\n{path}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))
