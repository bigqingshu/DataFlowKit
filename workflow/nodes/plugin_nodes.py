# -*- coding: utf-8 -*-
"""Pure helpers for plugin workflow nodes."""

import json
from datetime import datetime

from core.data_utils import normalize_rows


PLUGIN_ERROR_HEADERS = ["插件ID", "错误信息", "错误堆栈"]


def make_plugin_input_data(plugin_id, headers, rows, input_tables, lazy_schema=False):
    meta = {"plugin_id": plugin_id}
    if lazy_schema:
        meta["lazy_schema"] = True
    return {
        "type": "table",
        "headers": list(headers),
        "rows": [list(r) for r in rows],
        "source_name": "workflow_current",
        "meta": meta,
        "tables": input_tables,
    }


def normalize_plugin_logs(logs, plugin_id="", node_name="插件节点", now_text=None):
    """把插件返回的 logs 统一转为 dict 列表，便于写文件/SQLite/中转副表。"""
    normalized = []
    now = now_text or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if logs is None:
        logs = []
    if isinstance(logs, (str, bytes)):
        logs = [logs.decode("utf-8", "ignore") if isinstance(logs, bytes) else logs]
    if isinstance(logs, dict):
        logs = [logs]
    for item in logs:
        if isinstance(item, dict):
            normalized.append({
                "time": item.get("time") or now,
                "level": str(item.get("level", "INFO")).upper(),
                "plugin_id": item.get("plugin_id") or plugin_id,
                "node_name": item.get("node_name") or node_name,
                "object": item.get("object", ""),
                "message": item.get("message", item.get("msg", "")),
                "traceback": item.get("traceback", ""),
            })
        else:
            normalized.append({
                "time": now,
                "level": "INFO",
                "plugin_id": plugin_id,
                "node_name": node_name,
                "object": "",
                "message": str(item),
                "traceback": "",
            })
    return normalized


def plugin_log_items_to_table(log_items):
    headers = ["时间", "级别", "插件ID", "节点名称", "对象", "信息", "错误堆栈"]
    rows = [[
        it.get("time", ""), it.get("level", ""), it.get("plugin_id", ""),
        it.get("node_name", ""), it.get("object", ""), it.get("message", ""), it.get("traceback", "")
    ] for it in log_items]
    return headers, rows


def merge_plugin_output_fields_to_current(cur_headers, cur_rows, out_headers, out_rows):
    """按行号把插件输出字段合并到当前表；重名字段覆盖，缺失行补空。"""
    cur_headers = list(cur_headers or [])
    cur_rows = [list(r) for r in normalize_rows(cur_rows, len(cur_headers))]
    out_headers = list(out_headers or [])
    out_rows = [list(r) for r in normalize_rows(out_rows, len(out_headers))]
    merged_headers = list(cur_headers)
    for h in out_headers:
        if h not in merged_headers:
            merged_headers.append(h)
    total = max(len(cur_rows), len(out_rows))
    result = []
    cur_index = {h: i for i, h in enumerate(cur_headers)}
    out_index = {h: i for i, h in enumerate(out_headers)}
    for i in range(total):
        base = []
        cur_row = cur_rows[i] if i < len(cur_rows) else []
        out_row = out_rows[i] if i < len(out_rows) else []
        for h in merged_headers:
            if h in out_index and i < len(out_rows):
                oi = out_index[h]
                base.append(out_row[oi] if oi < len(out_row) else "")
            else:
                ci = cur_index.get(h)
                base.append(cur_row[ci] if ci is not None and ci < len(cur_row) else "")
        result.append(base)
    return merged_headers, result


def is_external_plugin_mode(config, item=None):
    mode = str(config.get("run_mode", "")).strip()
    if mode in ("插件独立环境", "external_python", "独立环境"):
        return True
    if item:
        default_mode = str(item.get("run_mode_default", item.get("info", {}).get("run_mode", ""))).strip()
        if not mode and default_mode in ("插件独立环境", "external_python", "独立环境"):
            return True
    return False


def normalize_plugin_output_schema(schema, fallback_headers=None):
    """把插件声明的输出 schema 规整为 table dict。"""
    fallback_headers = list(fallback_headers or [])
    if schema is None:
        return None
    if isinstance(schema, (list, tuple)):
        headers = [str(h) for h in schema]
        return {"type": "table", "headers": headers, "rows": [], "meta": {"lazy_schema": True}}
    if isinstance(schema, dict):
        if "output" in schema and isinstance(schema.get("output"), dict):
            schema = schema.get("output")
        headers = (
            schema.get("headers")
            or schema.get("fields")
            or schema.get("columns")
            or fallback_headers
        )
        rows = schema.get("rows", [])
        meta = dict(schema.get("meta") or {})
        meta.setdefault("lazy_schema", True)
        return {
            "type": schema.get("type", "table"),
            "headers": [str(h) for h in (headers or [])],
            "rows": [list(r) for r in (rows or [])],
            "meta": meta,
        }
    return None


def get_plugin_output_schema_table(item, input_data, params, plugin_context, fallback_headers=None):
    """优先调用插件 get_output_schema；未声明时读取元信息里的静态字段。"""
    module = item.get("module")
    schema = None
    provider = getattr(module, "get_output_schema", None) if module is not None else None
    if callable(provider):
        try:
            schema = provider(dict(params or {}), input_data, plugin_context)
        except Exception:
            schema = None
    if schema is None:
        info = item.get("info", {}) or {}
        schema = info.get("output_schema") or info.get("output_headers") or info.get("headers")
    return normalize_plugin_output_schema(schema, fallback_headers=fallback_headers)


def normalize_plugin_run_result(result, input_data, fallback_headers, fallback_rows):
    message = ""
    output = None
    logs = []
    summary = {}
    if isinstance(result, dict) and ("ok" in result or "output" in result):
        if result.get("ok", True) is False:
            raise RuntimeError(result.get("message") or "插件执行失败")
        message = result.get("message", "")
        logs = result.get("logs", []) or []
        summary = result.get("summary", {}) or {}
        output = result.get("output", input_data)
    else:
        output = result
    if output is None:
        output = input_data
    if not isinstance(output, dict):
        raise ValueError("插件返回值必须是 table dict 或包含 output 的 dict")
    if output.get("type", "table") != "table":
        raise ValueError(f"暂不支持插件输出类型：{output.get('type')}")
    return {
        "message": message,
        "logs": logs,
        "summary": summary,
        "headers": list(output.get("headers", fallback_headers)),
        "rows": [list(r) for r in output.get("rows", fallback_rows)],
    }


def build_plugin_failure_output(plugin_id, error_message, traceback_text, headers, rows, failure_policy):
    if failure_policy == "输出错误表继续":
        return list(PLUGIN_ERROR_HEADERS), [[plugin_id, error_message, traceback_text]]
    return list(headers), [list(r) for r in rows]


def should_save_plugin_output_as_transit(config):
    output_mode = config.get("output_mode", "使用插件返回结果")
    return bool(config.get("save_output_as_transit", False)) or str(output_mode).startswith("保存为中转副表")


def build_plugin_final_output(headers, rows, new_headers, new_rows, output_mode):
    if output_mode == "保存为中转副表并保持当前表":
        return list(headers), [list(r) for r in rows]
    if output_mode == "追加字段到当前表":
        return merge_plugin_output_fields_to_current(headers, rows, new_headers, new_rows)
    return list(new_headers), [list(r) for r in new_rows]


def build_plugin_probe_final_output(headers, rows, new_headers, new_rows, output_mode, schema_declared):
    if output_mode == "保存为中转副表并保持当前表":
        return list(headers), ([list(r) for r in rows] if not schema_declared else [])
    if output_mode == "追加字段到当前表":
        final_headers = list(headers)
        for h in new_headers:
            if h not in final_headers:
                final_headers.append(h)
        return final_headers, []
    return list(new_headers), [list(r) for r in new_rows]


def build_plugin_probe_stat(plugin_name, schema_declared, final_headers, transit_parts=None):
    if schema_declared:
        stat = f"插件 {plugin_name} 字段懒加载：未执行插件，已返回 {len(final_headers)} 个字段"
    else:
        stat = f"插件 {plugin_name} 字段懒加载：插件未声明输出字段，暂按上游字段透传"
    if transit_parts:
        stat += "；" + "；".join(transit_parts)
    return stat


def build_plugin_status_text(plugin_name, plugin_id, ok, failure_policy, message, summary, transit_parts, log_saved_parts, log_items):
    short_log = "；".join(str(x.get("message", x)) if isinstance(x, dict) else str(x) for x in (log_items or [])[:3])
    stat_parts = [f"插件 {plugin_name or plugin_id} 完成"]
    if not ok:
        stat_parts.append(f"失败处理：{failure_policy}")
    if message:
        stat_parts.append(str(message))
    if summary:
        try:
            stat_parts.append("摘要:" + json.dumps(summary, ensure_ascii=False)[:200])
        except Exception:
            pass
    if transit_parts:
        stat_parts.extend(transit_parts)
    if log_saved_parts:
        stat_parts.extend(log_saved_parts)
    if short_log:
        stat_parts.append(short_log)
    return "；".join(stat_parts)
