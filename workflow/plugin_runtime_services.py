# -*- coding: utf-8 -*-
"""Service helpers for plugin runtime context and external processes."""

import copy
import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime

from plugin_runtime.progress import handle_plugin_stdout_line


def get_runtime_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_external_python(config, item=None, allow_current=False, return_info=False):
    """查找外部插件 Python。"""
    py = str(config.get("external_python", "")).strip()
    if py and os.path.exists(py):
        return (py, False, "") if return_info else py
    env_dir = str(config.get("external_env_dir", "")).strip()
    if env_dir:
        candidates = [
            os.path.join(env_dir, "Scripts", "python.exe"),
            os.path.join(env_dir, "bin", "python"),
            os.path.join(env_dir, "python.exe"),
            os.path.join(env_dir, "python"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return (c, False, "") if return_info else c
    if allow_current and not getattr(sys, "frozen", False):
        warn = "未找到插件独立 Python，当前处于源码运行模式，已回退使用主程序 Python。正式使用独立环境插件时建议配置 plugin_envs/插件ID/Scripts/python.exe。"
        return (sys.executable, True, warn) if return_info else sys.executable
    raise FileNotFoundError("未找到插件独立 Python。请在插件节点中选择 plugin_envs/插件ID/Scripts/python.exe，或先创建插件独立环境。")


def make_external_plugin_json_context(window, config, context=None, execute_actions=False):
    plugin_id = config.get("plugin_id", "")
    context = context or {}
    snapshot = context.get("workflow_snapshot", {}) if isinstance(context, dict) else {}
    db_path = str(snapshot.get("db_path", "")).strip()
    workflow_name = str(snapshot.get("workflow_name", "")).strip()
    app_dir = snapshot.get("app_dir") or getattr(window.app, "app_dir", get_runtime_app_dir())
    if not db_path:
        # 兼容非后台/旧入口调用；后台线程应优先走 snapshot。
        db_path = window.get_workflow_db_path(context)
    if not workflow_name:
        workflow_name = window.get_workflow_output_table(context)
    return {
        "app_dir": app_dir,
        # 独立进程不接收真实数据库路径。需要落库时返回 database_requests，
        # 由主程序在当前节点权限上下文中统一执行。
        "db_path": "",
        "database_access": "managed_requests",
        "database_available": bool(db_path),
        "plugins_dir": window.get_plugins_dir(),
        "plugin_data_dir": window.get_plugin_data_dir(plugin_id),
        "log_dir": window.get_plugin_log_dir(),
        "is_preview": not bool(execute_actions),
        "execute_actions": bool(execute_actions),
        "is_config_probe": bool(context.get("is_config_probe")),
        "workflow_name": workflow_name,
        "node_name": config.get("name") or config.get("node_name") or "插件节点",
        "plugin_id": plugin_id,
        "transit_tables": context.get("transit_tables", {}),
        "input_tables": context.get("input_tables", {}),
        "plugin_input_table_specs": copy.deepcopy(config.get("input_tables", [])),
    }


def run_external_plugin_process(window, item, input_data, params, config, context=None, execute_actions=False):
    """使用独立 Python 环境运行插件。"""
    plugin_id = config.get("plugin_id", item.get("id", "plugin"))
    context = context or {}
    logs = []
    progress_callback = context.get("progress_callback")
    cancel_event = context.get("cancel_event")

    python_exe, used_current_fallback, fallback_warning = window.find_external_python(
        config,
        item,
        allow_current=True,
        return_info=True,
    )
    if fallback_warning:
        logs.append({"level": "WARNING", "message": fallback_warning})
        if callable(progress_callback):
            try:
                progress_callback({
                    "type": "node_progress",
                    "node_name": config.get("name") or "插件节点",
                    "plugin_id": plugin_id,
                    "message": fallback_warning,
                })
            except Exception:
                pass

    entry = str(config.get("external_entry") or item.get("external_entry") or item.get("path") or "").strip()
    if not entry:
        raise FileNotFoundError("未配置外部插件入口文件")
    if not os.path.isabs(entry):
        entry = os.path.join(window.get_plugins_dir(), entry)
    if not os.path.exists(entry):
        raise FileNotFoundError(f"外部插件入口不存在：{entry}")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_dir = os.path.join(window.get_plugin_data_dir(plugin_id), "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    input_path = os.path.join(run_dir, "input.json")
    output_path = os.path.join(run_dir, "output.json")
    payload = {
        "input_data": input_data,
        "params": params,
        "context": window.make_external_plugin_json_context(config, context, execute_actions=execute_actions),
    }
    with open(input_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    cmd = [python_exe, entry, "--input", input_path, "--output", output_path]
    timeout_text = str(config.get("external_timeout", "0") or "0").strip()
    try:
        timeout = float(timeout_text)
    except Exception:
        timeout = 0.0
    start_time = time.time()
    stdout_queue = queue.Queue()
    stdout_done = threading.Event()

    def stdout_reader(pipe):
        try:
            if pipe is None:
                return
            for line in iter(pipe.readline, ""):
                stdout_queue.put(line)
        except Exception as e:
            stdout_queue.put(json.dumps(
                {"type": "node_log", "level": "WARNING", "message": f"读取外部插件输出失败：{e}"},
                ensure_ascii=False,
            ))
        finally:
            stdout_done.set()
            try:
                if pipe is not None:
                    pipe.close()
            except Exception:
                pass

    def terminate_process(proc, exc):
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
        except Exception:
            try:
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
        raise exc

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    reader_thread = threading.Thread(target=stdout_reader, args=(proc.stdout,), daemon=True)
    reader_thread.start()
    code = None
    try:
        while True:
            drained = 0
            while drained < 200:
                try:
                    line = stdout_queue.get_nowait()
                except queue.Empty:
                    break
                handle_plugin_stdout_line(
                    line,
                    logs,
                    progress_callback=progress_callback,
                    node_name=config.get("name") or "插件节点",
                    plugin_id=plugin_id,
                )
                drained += 1

            if cancel_event is not None and cancel_event.is_set():
                terminate_process(proc, RuntimeError("用户取消外部插件执行"))
            if timeout > 0 and (time.time() - start_time) > timeout:
                terminate_process(proc, TimeoutError(f"外部插件执行超时：{timeout}秒"))

            code = proc.poll()
            if code is not None and stdout_done.is_set() and stdout_queue.empty():
                break
            time.sleep(0.05)

        code = proc.wait(timeout=1)
    finally:
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            reader_thread.join(timeout=1)
        except Exception:
            pass

    if not os.path.exists(output_path):
        if code != 0:
            raise RuntimeError(f"外部插件进程返回错误码：{code}，且未生成 output.json。运行目录：{run_dir}")
        raise FileNotFoundError(f"外部插件未生成 output.json：{output_path}")
    with open(output_path, "r", encoding="utf-8") as f:
        result = json.load(f)
    if isinstance(result, dict):
        old_logs = result.get("logs", []) or []
        if logs:
            result["logs"] = old_logs + logs
        if result.get("ok", True):
            window.execute_external_plugin_database_requests(
                result,
                config,
                context,
                execute_actions=execute_actions,
            )
        if used_current_fallback:
            summary = result.get("summary", {}) or {}
            summary["used_current_python_fallback"] = True
            summary["actual_python"] = python_exe
            result["summary"] = summary
        if code != 0 and result.get("ok", True):
            result["ok"] = False
            result["message"] = result.get("message") or f"外部插件进程返回错误码：{code}"
    return result


def execute_external_plugin_database_requests(window, result, config, context=None, execute_actions=False):
    if not isinstance(result, dict):
        return []
    requests = [item for item in (result.get("database_requests") or []) if isinstance(item, dict)]
    if not requests:
        return []
    logs = result.setdefault("logs", [])
    if not execute_actions:
        logs.append({
            "level": "INFO",
            "message": f"预览模式未执行外部插件数据库请求：{len(requests)} 项",
        })
        result["database_results"] = [
            {"status": "preview_skipped", "operation": item.get("operation", "")}
            for item in requests
        ]
        return result["database_results"]

    manager = window.get_table_manager(
        context if isinstance(context, dict) else None,
        node_type="插件节点",
        node_name=config.get("name") or config.get("node_name") or "插件节点",
    )
    results = []
    for index, request in enumerate(requests, start=1):
        operation = str(request.get("operation", "") or "").strip()
        if operation != "write_table":
            raise ValueError(f"外部插件数据库请求不支持操作：{operation or '<empty>'}")
        table_name = str(request.get("table_name", "") or "").strip()
        headers = list(request.get("headers") or [])
        rows = [list(row) for row in (request.get("rows") or [])]
        mode = request.get("mode") or "replace"
        info = manager.write_table(table_name, headers, rows, mode=mode)
        results.append({
            "status": "ok",
            "request_index": index,
            "operation": operation,
            **info,
        })
        logs.append({
            "level": "INFO",
            "message": f"主程序已执行外部插件数据库请求 {index}/{len(requests)}：{table_name}",
        })
    result["database_results"] = results
    if isinstance(context, dict) and results:
        context["needs_refresh_table_list"] = True
    return results


def make_plugin_context(window, config, context=None, execute_actions=False):
    plugin_id = config.get("plugin_id", "")
    context = context or {}
    snapshot = context.get("workflow_snapshot", {}) if isinstance(context, dict) else {}
    db_path = str(snapshot.get("db_path", "")).strip()
    if not db_path:
        # 兼容非后台/旧入口调用；后台线程应优先走 snapshot。
        db_path = window.get_workflow_db_path(context)
    workflow_name = str(snapshot.get("workflow_name", "")).strip()
    if not workflow_name:
        workflow_name = window.get_workflow_output_table(context)
    app_dir = snapshot.get("app_dir") or getattr(window.app, "app_dir", get_runtime_app_dir())
    node_name = config.get("name") or config.get("node_name") or "插件节点"
    progress_callback = context.get("progress_callback")
    cancel_event = context.get("cancel_event")

    def report_progress(current=None, total=None, message="", **extra):
        """给插件使用的轻量进度上报函数。"""
        if not callable(progress_callback):
            return
        msg = {
            "type": "node_progress",
            "node_name": node_name,
            "plugin_id": plugin_id,
            "current": current,
            "total": total,
            "message": message or "插件处理中",
        }
        msg.update(extra)
        try:
            progress_callback(msg)
        except Exception:
            pass

    return {
        "app_dir": app_dir,
        "db_path": db_path,
        "db": window.get_table_manager(context, node_type="插件节点", node_name=node_name),
        "plugins_dir": window.get_plugins_dir(),
        "plugin_data_dir": window.get_plugin_data_dir(plugin_id),
        "log_dir": window.get_plugin_log_dir(),
        "is_preview": not bool(execute_actions),
        "execute_actions": bool(execute_actions),
        "is_config_probe": bool(context.get("is_config_probe")),
        "workflow_name": workflow_name,
        "node_name": node_name,
        "plugin_id": plugin_id,
        "transit_tables": context.get("transit_tables", {}),
        "input_tables": context.get("input_tables", {}),
        "plugin_input_table_specs": copy.deepcopy(config.get("input_tables", [])),
        # 后台进度 / 取消透传给插件。
        # progress_callback 是底层消息通道；report_progress 是推荐给插件使用的轻量封装。
        "progress_callback": progress_callback,
        "report_progress": report_progress,
        "cancel_event": cancel_event,
    }
