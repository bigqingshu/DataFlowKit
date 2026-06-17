# -*- coding: utf-8 -*-
"""Service helpers for plugin log persistence and plugin transit outputs."""

import os
import re
from datetime import datetime

from db import TableAccessManager
from workflow.nodes.plugin_nodes import plugin_log_items_to_table as workflow_plugin_log_items_to_table


def save_plugin_logs_to_file(window, plugin_id, log_items):
    if not log_items:
        return ""
    log_dir = window.get_plugin_log_dir()
    os.makedirs(log_dir, exist_ok=True)
    safe_id = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", str(plugin_id or "plugin"))
    path = os.path.join(log_dir, f"{safe_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    with open(path, "w", encoding="utf-8") as f:
        for it in log_items:
            f.write(
                f"[{it.get('time','')}] [{it.get('level','INFO')}] "
                f"[{it.get('plugin_id','')}] {it.get('object','')} {it.get('message','')}\n"
            )
            tb = it.get("traceback") or ""
            if tb:
                f.write(str(tb).rstrip() + "\n")
    return path


def save_plugin_logs_to_sqlite(window, log_items, db_path=None, context=None):
    if not log_items:
        return 0
    db_path = str(db_path or "").strip()
    if not db_path:
        db_path = window.get_workflow_db_path(context)
    if not db_path:
        return 0
    if isinstance(context, dict):
        manager = window.get_table_manager(context, node_type="插件日志")
        if not manager.db_path:
            current = context.get("current_node_info", {}) if isinstance(context.get("current_node_info"), dict) else {}
            manager = TableAccessManager(
                db_path,
                node_id=current.get("node_id", ""),
                node_name=current.get("node_name", ""),
                node_type=current.get("node_type", "插件日志"),
                context=context,
                table_access=current.get("table_access") if isinstance(current.get("table_access"), dict) else None,
            )
        return manager.write_plugin_logs(log_items)
    return TableAccessManager(db_path, node_type="插件日志").write_plugin_logs(log_items)


def plugin_log_items_to_table(log_items):
    return workflow_plugin_log_items_to_table(log_items)


def save_plugin_output_to_transit(window, context, name, headers, rows, conflict_mode="覆盖", source="插件输出"):
    if context is None:
        return "未保存：无上下文"
    transit_tables = context.setdefault("transit_tables", {})
    base_name = str(name or "插件输出").strip() or "插件输出"
    headers = list(headers or [])
    rows = [list(r) for r in (rows or [])]
    exists_before = base_name in transit_tables
    if conflict_mode == "自动加时间戳":
        manager = window.check_transit_table_write_permission(
            context,
            base_name,
            exists=exists_before,
            write_mode=conflict_mode,
            fields=headers,
            node_type="插件节点",
        )
        final_name = window.make_unique_transit_name(base_name, transit_tables)
        transit_tables[final_name] = {"headers": headers, "rows": rows, "source": source}
        window.log_transit_table_event(
            manager,
            "write_transit_table",
            final_name,
            headers,
            rows,
            write_mode=conflict_mode,
            message=f"写入中转副表 {final_name}：{len(rows)} 行 × {len(headers)} 列",
        )
        return f"中转副表：{final_name}"
    if conflict_mode == "追加" and base_name in transit_tables:
        manager = window.check_transit_table_write_permission(
            context,
            base_name,
            exists=True,
            write_mode=conflict_mode,
            fields=headers,
            node_type="插件节点",
        )
        old = transit_tables.get(base_name, {}) or {}
        mh, mr = window.append_headers_rows(old.get("headers", []), old.get("rows", []), headers, rows)
        transit_tables[base_name] = {"headers": mh, "rows": mr, "source": f"{source}:追加"}
        window.log_transit_table_event(
            manager,
            "append_transit_table",
            base_name,
            mh,
            mr,
            write_mode=conflict_mode,
            appended_rows=len(rows),
            message=f"追加中转副表 {base_name}：新增 {len(rows)} 行，累计 {len(mr)} 行",
        )
        return f"中转副表追加：{base_name}（新增 {len(rows)} 行，累计 {len(mr)} 行）"
    manager = window.check_transit_table_write_permission(
        context,
        base_name,
        exists=exists_before,
        write_mode=conflict_mode or "覆盖",
        fields=headers,
        node_type="插件节点",
    )
    transit_tables[base_name] = {"headers": headers, "rows": rows, "source": source}
    window.log_transit_table_event(
        manager,
        "write_transit_table",
        base_name,
        headers,
        rows,
        write_mode=conflict_mode or "覆盖",
        message=f"写入中转副表 {base_name}：{len(rows)} 行 × {len(headers)} 列",
    )
    return f"中转副表：{base_name}"


def save_plugin_log_outputs(window, plugin_id, plugin_name, config, log_items, plugin_context=None,
                            context=None, execute_actions=False, include_transit=True,
                            suppress_errors=False):
    log_saved_parts = []
    plugin_context = plugin_context or {}
    should_save_persistent = execute_actions or config.get("plugin_log_in_preview", False)
    if config.get("save_plugin_log_file", True) and should_save_persistent:
        try:
            path = window.save_plugin_logs_to_file(plugin_id, log_items)
            if path:
                log_saved_parts.append(f"日志文件：{path}")
        except Exception as e:
            if not suppress_errors:
                log_saved_parts.append(f"日志文件保存失败：{e}")
    if config.get("save_plugin_log_sqlite", False) and should_save_persistent:
        try:
            cnt = window.save_plugin_logs_to_sqlite(log_items, db_path=plugin_context.get("db_path"), context=context)
            if cnt:
                log_saved_parts.append(f"SQLite日志：{cnt}条")
        except Exception as e:
            if not suppress_errors:
                log_saved_parts.append(f"SQLite日志保存失败：{e}")
    if include_transit and config.get("save_plugin_log_transit", False):
        try:
            lh, lr = window.plugin_log_items_to_table(log_items)
            log_name = config.get("plugin_log_transit_name") or f"{plugin_name or plugin_id}_日志"
            part = window.save_plugin_output_to_transit(
                context,
                log_name,
                lh,
                lr,
                config.get("transit_conflict_mode", "覆盖"),
                source=f"插件日志:{plugin_id}",
            )
            log_saved_parts.append(part)
        except Exception as e:
            if not suppress_errors:
                log_saved_parts.append(f"日志中转保存失败：{e}")
    return log_saved_parts
