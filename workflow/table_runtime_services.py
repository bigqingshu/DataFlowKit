# -*- coding: utf-8 -*-
"""Service helpers for workflow table access, reads, and audit logs."""

import os

from core.data_utils import normalize_rows
from db import TableAccessManager


def get_table_manager(window, context=None, node=None, node_type="", node_name=""):
    db_path = window.get_workflow_db_path(context)
    if isinstance(context, dict) and "table_access_policy" not in context:
        snapshot = context.get("workflow_snapshot") or {}
        if isinstance(snapshot, dict) and snapshot.get("table_access_policy") is not None:
            context["table_access_policy"] = TableAccessManager.normalize_permission_policy(
                snapshot.get("table_access_policy")
            )
    current = (context or {}).get("current_node_info", {}) if isinstance(context, dict) else {}
    table_access = None
    if isinstance(node, dict):
        window.ensure_node_identity(node)
        node_id = node.get("node_id", "")
        node_name = node.get("name", node_name)
        node_type = node.get("type", node_type)
        table_access = node.get("table_access") if isinstance(node.get("table_access"), dict) else None
    else:
        node_id = current.get("node_id", "")
        node_name = current.get("node_name", node_name)
        node_type = current.get("node_type", node_type)
        table_access = current.get("table_access") if isinstance(current.get("table_access"), dict) else None
    return TableAccessManager(
        db_path,
        node_id=node_id,
        node_name=node_name,
        node_type=node_type,
        context=context,
        table_access=table_access,
    )


def get_workflow_output_manager(window, table_name, overwrite=False, context=None):
    db_path = window.get_workflow_db_path(context)
    exists = bool(db_path and os.path.exists(db_path) and TableAccessManager(db_path).table_exists(table_name))
    permissions = window.table_permission_set(
        read=bool(overwrite and exists),
        write=True,
        create=True,
        replace=bool(overwrite),
    )
    access = {
        "version": 1,
        "auto_generated": True,
        "system_scope": "workflow_output",
        "tables": [
            window.make_table_access_entry(
                "workflow_output",
                table_name,
                permissions=permissions,
                write_mode="replace_table" if overwrite else "timestamp_new",
                declared_by="workflow_output",
            )
        ],
    }
    policy = None
    if isinstance(context, dict):
        snapshot = context.get("workflow_snapshot") or {}
        policy = context.get("table_access_policy") or (
            snapshot.get("table_access_policy") if isinstance(snapshot, dict) else None
        )
    return TableAccessManager(
        db_path,
        node_id="__workflow_output__",
        node_name="工作流最终输出",
        node_type="工作流输出",
        context=context if isinstance(context, dict) else None,
        table_access=access,
        permission_policy=policy,
    )


def get_workflow_sqlite_columns(window, table_name, context=None):
    """执行期读取 SQLite 字段，后台线程使用快照中的 db_path。"""
    db_path = window.get_workflow_db_path(context)
    if not db_path:
        raise ValueError("请先设置 SQLite 数据库路径。")
    return window.get_table_manager(context).get_columns(table_name)


def save_result_to_sqlite(window, headers, rows, table_name_raw, overwrite=False, backup=True, context=None):
    db_path = window.get_workflow_db_path(context)
    if not db_path:
        raise ValueError("请先设置 SQLite 数据库路径。")
    table_name = window.app.sanitize_sql_name(table_name_raw, "计划结果")
    sql_columns = window.app.make_sql_columns(headers)
    if not sql_columns:
        raise ValueError("没有可写入的字段。")
    current = (context or {}).get("current_node_info", {}) if isinstance(context, dict) else {}
    if isinstance(current, dict) and current.get("node_id"):
        manager = window.get_table_manager(context, node_type="工作流输出")
    else:
        manager = window.get_workflow_output_manager(table_name, overwrite=overwrite, context=context)
    if overwrite and backup and manager.table_exists(table_name):
        manager.backup_table(table_name)
    mode = "replace" if overwrite else "timestamp"
    info = manager.write_table(table_name, sql_columns, window.normalize_rows(rows, len(sql_columns)), mode=mode)
    return info.get("table_name", table_name)


def save_result_to_sqlite_append(window, headers, rows, table_name_raw, context=None):
    table_name = window.app.sanitize_sql_name(table_name_raw, "中转数据")
    sql_columns = window.app.make_sql_columns(headers)
    if not sql_columns:
        raise ValueError("没有可写入的字段。")
    normalized_rows = normalize_rows(rows, len(sql_columns))
    info = window.get_table_manager(context, node_type="保存中转数据").write_table(
        table_name,
        sql_columns,
        normalized_rows,
        mode="append",
    )
    return info.get("table_name", table_name)


def sqlite_table_exists_by_name(window, table_name, context=None):
    db_path = window.get_workflow_db_path(context)
    if not db_path or not os.path.exists(db_path):
        return False
    try:
        return window.get_table_manager(context).table_exists(table_name)
    except Exception:
        return False


def load_target_table_rows_for_writeback(window, table_name, context=None):
    db_path = window.get_workflow_db_path(context)
    if not db_path or not os.path.exists(db_path):
        raise ValueError("SQLite 数据库路径不存在，请先选择数据库。")
    return window.get_table_manager(context, node_type="字段映射写入表").read_records(
        table_name,
        include_rowid=True,
        include_row_index=True,
    )


def backup_sqlite_table_for_writeback(window, table_name, context=None):
    return window.get_table_manager(context, node_type="字段映射写入表").backup_table(table_name)


def apply_writeback_updates_to_sqlite(window, table_name, actions, context=None):
    db_path = window.get_workflow_db_path(context)
    if not db_path or not os.path.exists(db_path):
        raise ValueError("SQLite 数据库路径不存在，请先选择数据库。")
    return window.get_table_manager(context, node_type="字段映射写入表").apply_cell_actions(
        table_name,
        actions,
        cancel_event=(context or {}).get("cancel_event"),
    )


def apply_writeback_transaction_to_sqlite(window, table_name, actions, target_fields, context=None):
    db_path = window.get_workflow_db_path(context)
    if not db_path or not os.path.exists(db_path):
        raise ValueError("SQLite 数据库路径不存在，请先选择数据库。")
    return window.get_table_manager(
        context,
        node_type="字段映射写入表",
    ).apply_writeback_transaction(
        table_name,
        actions,
        clear_fields=target_fields,
        cancel_event=(context or {}).get("cancel_event"),
    )


def clear_writeback_target_fields_in_sqlite(window, table_name, target_fields, context=None):
    fields = []
    existing = set(window.get_workflow_sqlite_columns(table_name, context))
    for field in target_fields or []:
        field = str(field or "").strip()
        if field and field in existing and field not in fields:
            fields.append(field)
    if not fields:
        return 0
    return window.get_table_manager(context, node_type="字段映射写入表").clear_fields(table_name, fields)


def transit_write_permissions_for_mode(exists=False, write_mode="", partial=False):
    required = TableAccessManager.required_permissions_for_write_mode(
        write_mode or "replace_table",
        exists=exists,
        partial=partial,
    )
    standard = TableAccessManager.normalize_write_mode(write_mode)
    if standard in {"overlay_by_order", "write_fields_only", "fill_blank_fields", "clear_keep_schema"}:
        required.append("alter_schema")
    result = []
    for perm in required:
        if perm not in result:
            result.append(perm)
    return result


def check_transit_table_permission(window, context, table_name, permissions, operation="transit_table",
                                   fields=None, field_action=None, write_mode="", node_type=""):
    table_name = str(table_name or "").strip()
    if not table_name:
        return None
    manager = get_table_manager(
        window,
        context if isinstance(context, dict) else None,
        node_type=node_type or "中转副表",
    )
    manager.check_table_permission(
        table_name,
        permissions,
        operation=operation,
        fields=fields,
        field_action=field_action,
        write_mode=write_mode,
        source_type="中转副表",
    )
    return manager


def check_transit_table_write_permission(window, context, table_name, exists=False, write_mode="",
                                         fields=None, partial=False, node_type="",
                                         operation="write_transit_table"):
    return check_transit_table_permission(
        window,
        context,
        table_name,
        transit_write_permissions_for_mode(exists=exists, write_mode=write_mode, partial=partial),
        operation=operation,
        fields=fields,
        field_action="write",
        write_mode=write_mode,
        node_type=node_type,
    )


def log_transit_table_event(manager, operation, table_name, headers=None, rows=None, message="", **extra):
    if not isinstance(manager, TableAccessManager):
        return
    headers = list(headers or [])
    row_count = len(rows or [])
    extra.setdefault("source_type", "中转副表")
    extra.setdefault("rows", row_count)
    extra.setdefault("columns", len(headers))
    if not message:
        message = f"{operation} {table_name}：{row_count} 行 × {len(headers)} 列"
    manager._log_event(operation, table_name, message=message, **extra)


def check_current_table_permission(window, context, headers, write=False, operation="current_table"):
    manager = get_table_manager(
        window,
        context if isinstance(context, dict) else None,
        node_type="当前工作流表",
    )
    manager.check_table_permission(
        "__CURRENT_TABLE__",
        ["write_table", "update_rows"] if write else ["read_table"],
        operation=operation,
        fields=list(headers or []),
        field_action="write" if write else "read",
        write_mode="current_table_default" if write else "",
        source_type="当前工作流表",
    )
    return manager


def log_current_table_transform(manager, before_shape, headers, rows, node_type=""):
    if not isinstance(manager, TableAccessManager):
        return
    after_shape = (len(rows or []), len(headers or []))
    manager._log_event(
        "transform_current_table",
        "__CURRENT_TABLE__",
        source_type="当前工作流表",
        before_rows=before_shape[0],
        before_columns=before_shape[1],
        rows=after_shape[0],
        columns=after_shape[1],
        message=f"当前工作流表处理完成：{before_shape[0]}×{before_shape[1]} -> {after_shape[0]}×{after_shape[1]}，节点 {node_type}",
    )


def load_plan_table_records(window, table_name, context=None, required_fields=None):
    if str(table_name).startswith("中转:"):
        name = str(table_name).split(":", 1)[1]
        transit_tables = (context or {}).get("transit_tables", {})
        if name not in transit_tables:
            raise ValueError(f"中转副表不存在或尚未生成：{name}")
        item = transit_tables[name]
        all_columns = list(item.get("headers", []))
        columns = window.get_required_columns_for_plan_table(table_name, all_columns, required_fields)
        manager = window.check_transit_table_permission(
            context,
            table_name,
            ["read_table"],
            operation="read_transit_table",
            fields=columns,
            field_action="read",
            node_type="高级筛选",
        )
        column_indexes = [(all_columns.index(col), col) for col in columns]
        db_rows = window.normalize_rows(item.get("rows", []), len(all_columns))
        records = []
        for row in db_rows:
            record = {}
            for i, col in column_indexes:
                record[f"{table_name}.{col}"] = window.safe_cell(row, i)
            records.append(record)
        window.log_transit_table_event(
            manager,
            "read_transit_table",
            table_name,
            columns,
            db_rows,
            message=f"高级筛选读取中转副表 {table_name}：{len(db_rows)} 行 × {len(columns)} 列",
        )
        return records

    db_path = window.get_workflow_db_path(context)
    if not db_path or not os.path.exists(db_path):
        raise ValueError("当前 SQLite 数据库路径不存在，无法读取副表。")
    all_columns = window.get_workflow_sqlite_columns(table_name, context)
    columns = window.get_required_columns_for_plan_table(table_name, all_columns, required_fields)
    data = window.get_table_manager(context, node_type="高级筛选").read_table(table_name, fields=columns)
    db_rows = [list(row) for row in data.get("rows", [])]
    records = []
    for row in db_rows:
        record = {}
        for i, col in enumerate(columns):
            value = row[i] if i < len(row) else ""
            record[f"{table_name}.{col}"] = value
        records.append(record)
    return records


def load_lookup_table_for_match_value_output(window, config, context=None):
    """读取匹配值输出列名节点使用的匹配表，支持 SQLite 表与内存中转副表。"""
    lookup_source_type = str(config.get("lookup_source_type", "SQLite表")).strip() or "SQLite表"
    lookup_table = str(config.get("lookup_table", "")).strip()
    if not lookup_table:
        raise ValueError("请选择匹配表或中转副表。")
    if lookup_source_type == "中转副表":
        transit_tables = (context or {}).get("transit_tables", {})
        if lookup_table not in transit_tables:
            raise ValueError(f"中转副表不存在或尚未生成：{lookup_table}。请确认保存中转数据节点在当前节点之前执行。")
        item = transit_tables[lookup_table]
        columns = list(item.get("headers", []))
        manager = window.check_transit_table_permission(
            context,
            lookup_table,
            ["read_table"],
            operation="read_transit_table",
            fields=config.get("lookup_fields", []),
            field_action="read",
            node_type="匹配值输出列名",
        )
        raw_rows = window.normalize_rows(item.get("rows", []), len(columns))
        records = []
        for index, row in enumerate(raw_rows, start=1):
            record = {"__rowid__": "", "__row_index__": index}
            for i, col in enumerate(columns):
                record[col] = window.safe_cell(row, i)
            records.append(record)
        window.log_transit_table_event(
            manager,
            "read_transit_table",
            lookup_table,
            columns,
            raw_rows,
            message=f"匹配值输出列名读取中转副表 {lookup_table}：{len(raw_rows)} 行 × {len(columns)} 列",
        )
        return columns, records
    return window.load_target_table_rows_for_writeback(lookup_table, context=context)
