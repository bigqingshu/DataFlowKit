# -*- coding: utf-8 -*-
"""Window adapters for filesystem workflow nodes."""

import csv
import os
import sys

from workflow.nodes.file_nodes import (
    BATCH_RENAME_LOG_HEADERS,
    apply_batch_rename_node,
    apply_file_list_node,
    make_numbered_path,
)


def get_window_app_dir(window):
    app = getattr(window, "app", None)
    app_dir = getattr(app, "app_dir", None)
    if app_dir:
        return app_dir
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def report_window_node_progress(window, context, current=None, total=None, message="", node_name=""):
    window.report_workflow_node_progress(
        context,
        current=current,
        total=total,
        message=message,
        node_name=node_name,
    )


def make_file_node_context(window, context):
    node_context = dict(context or {})
    node_context.setdefault("default_directory", get_window_app_dir(window))
    node_context["check_cancelled"] = lambda index=None: window.check_workflow_cancelled(context)
    node_context["report_progress"] = (
        lambda current=None, total=None, message="", node_name="获取文件列表": report_window_node_progress(
            window,
            context,
            current=current,
            total=total,
            message=message,
            node_name=node_name,
        )
    )
    return node_context


def make_batch_rename_context(window, context):
    node_context = make_file_node_context(window, context)
    node_context.update({
        "path_exists": os.path.exists,
        "path_is_dir": os.path.isdir,
        "make_dirs": lambda path: os.makedirs(path, exist_ok=True),
        "rename_file": os.rename,
        "replace_file": os.replace,
        "make_numbered_path": make_numbered_path,
    })
    return node_context


def write_batch_rename_log(config, node_context):
    log_path = config.get("log_path") or os.path.abspath("rename_log.csv")
    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    with open(log_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(BATCH_RENAME_LOG_HEADERS)
        writer.writerows(node_context.get("batch_rename_log_rows", []))


def apply_file_list_node_for_window(window, headers, rows, config, context=None):
    node_context = make_file_node_context(window, context)
    return apply_file_list_node(headers, rows, config, context=node_context)


def apply_batch_rename_node_for_window(window, headers, rows, config, execute_actions=False, context=None):
    node_context = make_batch_rename_context(window, context)
    headers, rows, message = apply_batch_rename_node(
        headers,
        rows,
        config,
        execute_actions=execute_actions,
        context=node_context,
    )

    if node_context.get("batch_rename_do_rename") and bool(config.get("write_log", True)):
        try:
            write_batch_rename_log(config, node_context)
        except Exception as exc:
            changed = node_context.get("batch_rename_changed", 0)
            return headers, rows, f"重命名完成 {changed} 项，但日志写入失败：{exc}"

    return headers, rows, message
