# -*- coding: utf-8 -*-
"""Progress and log parsing helpers for plugin runtimes."""

import json


def handle_plugin_stdout_line(line, logs, progress_callback=None, node_name="插件节点", plugin_id=""):
    text = str(line or "").rstrip("\r\n")
    if not text:
        return
    try:
        msg = json.loads(text)
        if isinstance(msg, dict) and msg.get("type") in ("node_progress", "node_log", "log"):
            if callable(progress_callback):
                payload = dict(msg)
                payload.setdefault("type", "node_progress")
                payload.setdefault("node_name", node_name or "插件节点")
                payload.setdefault("plugin_id", plugin_id)
                progress_callback(payload)
            if msg.get("message"):
                logs.append({"level": msg.get("level", "INFO"), "message": msg.get("message")})
        else:
            logs.append({"level": "INFO", "message": text})
    except Exception:
        logs.append({"level": "INFO", "message": text})

