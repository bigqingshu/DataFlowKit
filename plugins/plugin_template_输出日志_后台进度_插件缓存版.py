# -*- coding: utf-8 -*-
"""
外部插件模板 - 支持数据库 API、输出/日志、后台进度、取消信号、插件内部缓存。

使用方法：
1. 把本文件复制到主程序同级目录 plugins/ 下。
2. 修改 PLUGIN_INFO["id"] 和 PLUGIN_INFO["name"]。
3. 按需修改 get_parameter_schema() 和 run()。
4. 在主程序计划窗口点击“刷新插件”。

缓存说明：
- 本模板演示“插件内部缓存”，不依赖主程序做全局节点缓存。
- 缓存文件默认保存在 context["plugin_data_dir"]/cache.sqlite。
- 适合 HEX/Word/Excel/图片识别/文件解析等耗时插件。
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


PLUGIN_INFO = {
    "id": "example_cached_plugin",
    "name": "示例缓存插件",
    "version": "1.2.0",
    "api_version": "1.0",
    "category": "示例",
    "description": "演示插件参数、数据库API、表格输出、后台进度、取消信号、插件内部缓存。",
    "input_type": "table",
    "output_type": "table",
    "danger_level": "safe_readonly",
}


# -----------------------------------------------------------------------------
# 参数定义
# -----------------------------------------------------------------------------
def get_parameter_schema():
    return [
        {
            "name": "path_field",
            "label": "文件路径字段",
            "type": "field_select",
            "default": "完整路径",
            "required": False,
            "help": "如果当前表里有完整路径字段，可选择该字段作为文件处理输入。",
        },
        {
            "name": "add_status",
            "label": "输出状态字段",
            "type": "bool",
            "default": True,
        },
        {
            "name": "output_prefix",
            "label": "输出字段前缀",
            "type": "text",
            "default": "插件_",
        },
        {
            "name": "sample_table",
            "label": "可选数据库表",
            "type": "table_select",
            "default": "",
            "help": "主程序内置模式可通过 context['db'] 读取；独立模式请配置为输入表。",
        },
        {
            "name": "enable_cache",
            "label": "启用插件缓存",
            "type": "bool",
            "default": True,
            "help": "文件和关键参数未变化时，直接复用上次处理结果。",
        },
        {
            "name": "force_refresh",
            "label": "强制重新处理，不使用缓存",
            "type": "bool",
            "default": False,
            "help": "勾选后忽略缓存，重新处理并覆盖缓存。",
        },
        {
            "name": "cache_key_mode",
            "label": "缓存校验方式",
            "type": "select",
            "default": "快速签名",
            "options": ["快速签名", "文件Hash"],
            "help": "快速签名=路径+大小+修改时间；文件Hash=额外计算sha256，更准确但更慢。",
        },
    ]


def get_output_schema(params=None, input_data=None, context=None):
    params = dict(params or {})
    input_data = input_data or {}
    headers = list(input_data.get("headers", []) or [])
    prefix = params.get("output_prefix", "插件_")
    add_status = bool(params.get("add_status", True))
    out_headers = list(headers)
    extra_headers = []
    if add_status:
        extra_headers.append(prefix + "状态")
    extra_headers.append(prefix + "缓存状态")
    extra_headers.append(prefix + "文件大小")
    for h in extra_headers:
        if h not in out_headers:
            out_headers.append(h)
    return {
        "type": "table",
        "headers": out_headers,
        "rows": [],
        "meta": {"plugin": PLUGIN_INFO["id"], "lazy_schema": True},
    }


def validate_params(params, input_data, context):
    # 返回 (True, "") 表示校验通过；返回 (False, "错误信息") 表示阻止执行。
    return True, ""


# -----------------------------------------------------------------------------
# 缓存辅助函数
# -----------------------------------------------------------------------------
def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _business_params_hash(params: Dict[str, Any]) -> str:
    """计算关键业务参数摘要，排除缓存控制参数。"""
    excluded = {"enable_cache", "force_refresh", "cache_key_mode"}
    effective = {k: v for k, v in dict(params).items() if k not in excluded}
    return _sha256_text(_json_dumps(effective))


def _file_signature(path: str, mode: str) -> Dict[str, Any]:
    p = Path(path)
    stat = p.stat()
    sig = {
        "path": str(p.resolve()),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }
    if mode == "文件Hash":
        sig["sha256"] = _sha256_file(str(p))
    return sig


def _make_cache_key(plugin_id: str, plugin_version: str, params: Dict[str, Any], file_path: str, mode: str) -> Tuple[str, Dict[str, Any], str]:
    sig = _file_signature(file_path, mode)
    params_hash = _business_params_hash(params)
    payload = {
        "plugin_id": plugin_id,
        "plugin_version": plugin_version,
        "params_hash": params_hash,
        "file_signature": sig,
    }
    return _sha256_text(_json_dumps(payload)), sig, params_hash


def _get_cache_db_path(context: Dict[str, Any]) -> str:
    plugin_data_dir = context.get("plugin_data_dir") or os.path.join(os.getcwd(), "plugin_data", PLUGIN_INFO["id"])
    os.makedirs(plugin_data_dir, exist_ok=True)
    return os.path.join(plugin_data_dir, "cache.sqlite")


def _ensure_cache_db(cache_db_path: str) -> None:
    with sqlite3.connect(cache_db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plugin_cache (
                cache_key TEXT PRIMARY KEY,
                plugin_id TEXT,
                plugin_version TEXT,
                file_path TEXT,
                file_size INTEGER,
                file_mtime_ns INTEGER,
                params_hash TEXT,
                result_json TEXT,
                updated_at TEXT
            )
            """
        )
        conn.commit()


def _load_cache(cache_db_path: str, cache_key: str) -> Optional[Dict[str, Any]]:
    _ensure_cache_db(cache_db_path)
    with sqlite3.connect(cache_db_path) as conn:
        cur = conn.execute("SELECT result_json FROM plugin_cache WHERE cache_key=?", (cache_key,))
        row = cur.fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except Exception:
        return None


def _save_cache(
    cache_db_path: str,
    cache_key: str,
    file_path: str,
    file_signature: Dict[str, Any],
    params_hash: str,
    result: Dict[str, Any],
) -> None:
    _ensure_cache_db(cache_db_path)
    result_json = _json_dumps(result)
    with sqlite3.connect(cache_db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO plugin_cache
            (cache_key, plugin_id, plugin_version, file_path, file_size, file_mtime_ns, params_hash, result_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cache_key,
                PLUGIN_INFO["id"],
                PLUGIN_INFO["version"],
                file_path,
                int(file_signature.get("size", 0)),
                int(file_signature.get("mtime_ns", 0)),
                params_hash,
                result_json,
                time.strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        conn.commit()


# -----------------------------------------------------------------------------
# 示例业务处理函数
# -----------------------------------------------------------------------------
def process_file_example(file_path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """示例文件处理逻辑。实际 HEX/Word/Excel 插件可替换这里。"""
    p = Path(file_path)
    return {
        "headers": ["文件大小", "处理状态"],
        "row": [str(p.stat().st_size), "已处理"],
        "logs": [f"处理文件：{file_path}"],
    }


# -----------------------------------------------------------------------------
# 插件入口
# -----------------------------------------------------------------------------
def run(input_data, params, context):
    headers = list(input_data.get("headers", []))
    rows = [list(r) for r in input_data.get("rows", [])]

    report = context.get("report_progress")
    cancel_event = context.get("cancel_event")

    prefix = params.get("output_prefix", "插件_")
    add_status = bool(params.get("add_status", True))
    path_field = params.get("path_field", "")

    enable_cache = bool(params.get("enable_cache", True))
    force_refresh = bool(params.get("force_refresh", False))
    cache_key_mode = params.get("cache_key_mode", "快速签名")

    out_headers = list(headers)
    extra_headers = []
    if add_status:
        extra_headers.append(prefix + "状态")
    extra_headers.append(prefix + "缓存状态")
    extra_headers.append(prefix + "文件大小")

    for h in extra_headers:
        if h not in out_headers:
            out_headers.append(h)

    status_idx = out_headers.index(prefix + "状态") if add_status else None
    cache_status_idx = out_headers.index(prefix + "缓存状态")
    file_size_idx = out_headers.index(prefix + "文件大小")

    path_idx = headers.index(path_field) if path_field in headers else -1
    cache_db_path = _get_cache_db_path(context)

    logs: List[Any] = []
    out_rows: List[List[str]] = []
    success = 0
    failed = 0
    cache_hit = 0
    cache_miss = 0

    total = len(rows)
    for i, row in enumerate(rows, start=1):
        if cancel_event is not None and cancel_event.is_set():
            return {
                "ok": False,
                "message": "用户取消插件执行",
                "output": {"type": "table", "headers": out_headers, "rows": out_rows or rows},
                "logs": logs + ["插件检测到取消信号，已安全停止。"],
                "summary": {"total": total, "success": success, "failed": failed, "cache_hit": cache_hit, "cache_miss": cache_miss},
            }

        row = list(row)
        while len(row) < len(out_headers):
            row.append("")

        file_path = row[path_idx] if path_idx >= 0 and path_idx < len(row) else ""
        try:
            if file_path and os.path.isfile(file_path):
                cache_key, sig, params_hash = _make_cache_key(
                    PLUGIN_INFO["id"], PLUGIN_INFO["version"], params, file_path, cache_key_mode
                )

                cached = None
                if enable_cache and not force_refresh:
                    cached = _load_cache(cache_db_path, cache_key)

                if cached:
                    cache_hit += 1
                    cache_state = "CACHE_HIT"
                    result = cached
                    logs.append({"level": "INFO", "object": file_path, "message": "CACHE_HIT：复用缓存结果"})
                else:
                    cache_miss += 1
                    cache_state = "CACHE_REFRESH" if force_refresh else "CACHE_MISS"
                    result = process_file_example(file_path, params)
                    if enable_cache:
                        _save_cache(cache_db_path, cache_key, file_path, sig, params_hash, result)
                        logs.append({"level": "INFO", "object": file_path, "message": f"{cache_state}：已重新处理并写入缓存"})

                # 示例：把处理结果中的 文件大小 写入输出字段
                result_headers = result.get("headers", [])
                result_row = result.get("row", [])
                if "文件大小" in result_headers:
                    row[file_size_idx] = str(result_row[result_headers.index("文件大小")])
                if status_idx is not None:
                    row[status_idx] = "成功"
                row[cache_status_idx] = cache_state
                success += 1
            else:
                if status_idx is not None:
                    row[status_idx] = "跳过"
                row[cache_status_idx] = "NO_FILE"
                logs.append({"level": "WARNING", "object": file_path, "message": "文件不存在或未配置文件路径字段，已跳过"})
                failed += 1
        except Exception as e:
            if status_idx is not None:
                row[status_idx] = "失败"
            row[cache_status_idx] = "ERROR"
            logs.append({"level": "ERROR", "object": file_path, "message": f"处理失败：{e}"})
            failed += 1

        out_rows.append(row)

        if callable(report):
            report(i, total, f"插件处理 {i}/{total}")

    # 示例：使用数据库 API 读取表名。
    table_count = 0
    try:
        table_count = len(context["db"].list_tables())
    except Exception as e:
        logs.append({"level": "WARNING", "message": f"读取数据库表名失败：{e}"})

    return {
        "ok": True,
        "message": f"示例缓存插件完成：成功 {success}，失败 {failed}，缓存命中 {cache_hit}，未命中 {cache_miss}",
        "output": {
            "type": "table",
            "headers": out_headers,
            "rows": out_rows,
            "meta": {"plugin_id": PLUGIN_INFO["id"], "cache_db": cache_db_path},
        },
        "logs": logs,
        "summary": {
            "total": total,
            "success": success,
            "failed": failed,
            "cache_hit": cache_hit,
            "cache_miss": cache_miss,
            "db_table_count": table_count,
        },
    }
