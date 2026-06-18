# -*- coding: utf-8 -*-
"""Common app/context helpers for PlanWorkflowWindow."""

import os
import sys
import traceback
import uuid
from datetime import datetime

from db import TableAccessManager
from workflow.workflow_task_snapshot_mixin import get_workflow_task_app_dir


class WorkflowAppSupportMixin:
    """Compatibility methods for workflow app context and logging."""

    def get_sqlite_table_names(self):
        db_path = self.app.db_path_var.get().strip()
        if not db_path or not os.path.exists(db_path):
            return []
        try:
            return TableAccessManager(db_path).list_tables()
        except Exception:
            return []

    def get_workflow_snapshot(self, context=None):
        """返回后台任务快照。后台线程优先使用快照，避免直接读取 Tkinter 变量。"""
        if isinstance(context, dict):
            snapshot = context.get("workflow_snapshot") or {}
            if isinstance(snapshot, dict):
                return snapshot
        return {}

    def get_workflow_db_path(self, context=None):
        """执行期统一获取 SQLite 路径：优先读 workflow_snapshot，兜底读主线程 UI 变量。"""
        snapshot = self.get_workflow_snapshot(context)
        db_path = str(snapshot.get("db_path") or "").strip()
        if db_path:
            return db_path
        try:
            return self.app.db_path_var.get().strip()
        except Exception:
            return ""

    def make_node_id(self):
        return "node_" + uuid.uuid4().hex[:12]

    def get_workflow_log_dir(self):
        log_dir = os.path.join(get_workflow_task_app_dir(self), "logs", "workflow")
        os.makedirs(log_dir, exist_ok=True)
        return log_dir

    def write_workflow_error_log(self, mode, message, traceback_text="", logs=None, snapshot=None):
        """后台线程错误日志。只写文件，不直接操作 Tkinter。"""
        try:
            log_dir = self.get_workflow_log_dir()
            path = os.path.join(log_dir, f"workflow_error_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.log")
            snapshot = snapshot or {}
            node_count = len(snapshot.get("nodes", self.nodes) or [])
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"任务模式：{mode}\n")
                f.write(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"节点数量：{node_count}\n")
                if snapshot.get("db_path"):
                    f.write(f"数据库：{snapshot.get('db_path')}\n")
                if snapshot.get("workflow_name"):
                    f.write(f"工作流/输出名：{snapshot.get('workflow_name')}\n")
                f.write(f"错误信息：{message}\n\n")
                if logs:
                    f.write("执行日志：\n")
                    for item in logs:
                        f.write(f"- {item}\n")
                    f.write("\n")
                if traceback_text:
                    f.write("Traceback：\n")
                    f.write(traceback_text)
            return path
        except Exception:
            return ""
