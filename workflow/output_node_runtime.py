# -*- coding: utf-8 -*-
"""Window adapters for output/write workflow nodes."""

import os
import sys

from core.data_utils import normalize_rows
from workflow.nodes.selected_columns_nodes import (
    apply_selected_columns_to_memory_table,
    build_selected_columns_write_payload,
    build_selected_columns_write_preview_rows,
    get_selected_columns_write_skip_stat,
    normalize_selected_columns_write_mode,
    resolve_selected_columns_write_target,
)
from workflow.nodes.transit_nodes import apply_save_transit_node
from workflow.nodes.writeback_nodes import (
    apply_external_table_to_current_node,
    build_writeback_actions as build_writeback_actions_from_records,
    build_writeback_execute_stat,
    build_writeback_full_structure_execute_stat,
    build_writeback_full_structure_rows_for_sqlite,
    build_writeback_preview_stat,
    count_writeback_actions,
    finish_writeback_node_output,
    get_writeback_non_execute_suffix,
    get_writeback_target_fields,
    should_execute_writeback_update,
)


def get_window_app_dir(window):
    app = getattr(window, "app", None)
    app_dir = getattr(app, "app_dir", None)
    if app_dir:
        return app_dir
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_selected_columns_source_table(window, config, current_headers, current_rows, context=None):
    """Read source data for the selected-columns write node."""
    source_type = config.get("source_type", "当前工作流表")
    context = context or {"transit_tables": {}}
    if source_type == "当前工作流表":
        headers = list(current_headers)
        return headers, [list(r) for r in normalize_rows(current_rows, len(headers))], "当前工作流表"
    if source_type == "SQLite表":
        table = str(config.get("source_sqlite_table", "")).strip()
        if not table:
            raise ValueError("请选择 SQLite 来源表。")
        data = window.get_table_manager(context, node_type="选定列写入指定表").read_table(table)
        return list(data.get("headers", [])), [list(row) for row in data.get("rows", [])], f"SQLite:{table}"
    if source_type == "中转副表":
        name = str(config.get("source_transit_table", "")).strip()
        if not name:
            raise ValueError("请选择中转来源表。")
        manager = window.check_transit_table_permission(
            context,
            name,
            ["read_table"],
            operation="read_transit_table",
            field_action="read",
            node_type="选定列写入指定表",
        )
        item = (context.get("transit_tables", {}) or {}).get(name)
        if not item:
            raise ValueError(f"未找到中转来源表：{name}")
        headers = list(item.get("headers", []) or [])
        rows = [list(r) for r in (item.get("rows", []) or [])]
        window.log_transit_table_event(
            manager,
            "read_transit_table",
            name,
            headers,
            rows,
            message=f"读取中转来源表 {name}：{len(rows)} 行 × {len(headers)} 列",
        )
        return headers, rows, f"中转:{name}"
    raise ValueError(f"未知来源类型：{source_type}")


def read_selected_columns_target_table(window, config, context=None, current_headers=None, current_rows=None):
    """Read target data for the selected-columns write node."""
    target_type = config.get("target_type", "SQLite表")
    context = context or {"transit_tables": {}}
    if target_type == "当前工作表":
        headers = list(current_headers or [])
        return headers, [list(r) for r in normalize_rows(current_rows or [], len(headers))], "当前工作表"
    if target_type == "SQLite表":
        table = str(config.get("target_table", "")).strip()
        if not table:
            raise ValueError("请输入 SQLite 目标表。")
        try:
            real_table = window.app.sanitize_sql_name(table, "选定列结果")
            if not sqlite_table_exists_by_name(window, real_table, context=context):
                return [], [], f"SQLite:{table}"
            data = window.get_table_manager(context, node_type="选定列写入指定表").read_table(real_table)
            return list(data.get("headers", [])), [list(row) for row in data.get("rows", [])], f"SQLite:{real_table}"
        except Exception:
            return [], [], f"SQLite:{table}"
    if target_type == "中转副表":
        name = str(config.get("target_transit_table", "")).strip() or "选定列结果"
        manager = window.check_transit_table_permission(
            context,
            name,
            ["read_table"],
            operation="read_transit_table",
            field_action="read",
            node_type="选定列写入指定表",
        )
        item = (context.get("transit_tables", {}) or {}).get(name)
        if not item:
            window.log_transit_table_event(
                manager,
                "read_transit_table",
                name,
                [],
                [],
                message=f"读取中转目标表 {name}：目标尚不存在",
            )
            return [], [], f"中转:{name}"
        headers = list(item.get("headers", []) or [])
        rows = [list(r) for r in (item.get("rows", []) or [])]
        window.log_transit_table_event(
            manager,
            "read_transit_table",
            name,
            headers,
            rows,
            message=f"读取中转目标表 {name}：{len(rows)} 行 × {len(headers)} 列",
        )
        return headers, rows, f"中转:{name}"
    raise ValueError(f"未知目标类型：{target_type}")


def build_selected_columns_write_preview(window, config, current_headers, current_rows, context=None):
    source_headers, source_rows, source_name = read_selected_columns_source_table(
        window,
        config,
        current_headers,
        current_rows,
        context,
    )
    target_headers, target_rows, target_name = read_selected_columns_target_table(
        window,
        config,
        context,
        current_headers,
        current_rows,
    )
    return build_selected_columns_write_preview_rows(
        config,
        source_headers,
        source_rows,
        source_name,
        target_headers,
        target_rows,
        target_name,
    )


def get_selected_columns_write_payload(window, config, current_headers, current_rows, context=None):
    source_headers, source_rows, source_name = read_selected_columns_source_table(
        window,
        config,
        current_headers,
        current_rows,
        context,
    )
    selected_fields, target_fields, selected_rows = build_selected_columns_write_payload(
        config,
        source_headers,
        source_rows,
    )
    return selected_fields, target_fields, selected_rows, source_name


def apply_selected_columns_write_current_table(window, headers, rows, config, target_fields, selected_rows):
    new_headers, new_rows = apply_selected_columns_to_memory_table(headers, rows, target_fields, selected_rows, config)
    return new_headers, new_rows, f"已写入当前工作表：{len(new_rows)} 行 × {len(new_headers)} 列，结果继续传给后续节点"


def apply_selected_columns_write_transit_table(window, headers, rows, config, context, target_name, target_fields, selected_rows):
    mode = normalize_selected_columns_write_mode(config.get("write_mode", "局部覆盖，保留目标原行数"))
    exists_before = target_name in context["transit_tables"]
    manager = window.check_transit_table_write_permission(
        context,
        target_name,
        exists=exists_before,
        write_mode=mode,
        fields=target_fields,
        partial=mode in ("局部覆盖，保留目标原行数", "清空目标字段后覆盖，保留目标原行数"),
        node_type="选定列写入指定表",
    )
    old = context["transit_tables"].get(target_name, {}) or {}
    old_headers = list(old.get("headers", []) or [])
    old_rows = [list(r) for r in (old.get("rows", []) or [])]
    new_headers, new_rows = apply_selected_columns_to_memory_table(old_headers, old_rows, target_fields, selected_rows, config)
    context["transit_tables"][target_name] = {
        "headers": new_headers,
        "rows": [list(r) for r in new_rows],
        "source": "选定列写入指定表",
    }
    window.log_transit_table_event(
        manager,
        "write_transit_table",
        target_name,
        new_headers,
        new_rows,
        write_mode=mode,
        message=f"写入中转副表 {target_name}：{len(new_rows)} 行 × {len(new_headers)} 列，模式 {mode}",
    )
    return headers, rows, f"已写入中转副表：{target_name}（{len(new_rows)} 行 × {len(new_headers)} 列），主流程数据透传"


def apply_selected_columns_write_sqlite_table(window, headers, rows, config, context, target_name, target_fields, selected_rows):
    sqlite_name = window.app.sanitize_sql_name(target_name, "选定列结果")
    mode = normalize_selected_columns_write_mode(config.get("write_mode", "复制列到目标表新建字段"))
    if mode == "覆盖重建目标表":
        saved = window.save_result_to_sqlite(
            target_fields,
            selected_rows,
            sqlite_name,
            overwrite=True,
            backup=bool(config.get("backup_before_write", True)),
            context=context,
        )
        return headers, rows, f"已覆盖重建 SQLite 表：{saved}（{len(selected_rows)} 行 × {len(target_fields)} 列），主流程数据透传"
    target_headers, target_rows, _target_label = read_selected_columns_target_table(
        window,
        {**config, "target_type": "SQLite表", "target_table": sqlite_name},
        context,
    )
    new_headers, new_rows = apply_selected_columns_to_memory_table(target_headers, target_rows, target_fields, selected_rows, config)
    saved = window.save_result_to_sqlite(
        new_headers,
        new_rows,
        sqlite_name,
        overwrite=True,
        backup=bool(config.get("backup_before_write", True)),
        context=context,
    )
    return headers, rows, f"已复制选定列到 SQLite 表字段：{saved}（{len(new_rows)} 行 × {len(new_headers)} 列），主流程数据透传"


def apply_selected_columns_write_node_for_window(window, headers, rows, config, context=None, execute_actions=False):
    context = context if context is not None else {"transit_tables": {}}
    context.setdefault("transit_tables", {})
    selected_fields, target_fields, selected_rows, source_name = get_selected_columns_write_payload(
        window,
        config,
        headers,
        rows,
        context,
    )
    target_type, target_name = resolve_selected_columns_write_target(config)
    allow_preview_write = bool(context.get("allow_selected_columns_write_in_preview", False))
    config_preview_only = bool(context.get("selected_columns_config_preview_only", False))
    skip_stat = get_selected_columns_write_skip_stat(
        config,
        source_name,
        selected_fields,
        selected_rows,
        execute_actions=execute_actions,
        allow_preview_write=allow_preview_write,
        config_preview_only=config_preview_only,
    )
    if skip_stat:
        return headers, rows, skip_stat

    if target_type == "当前工作表":
        return apply_selected_columns_write_current_table(window, headers, rows, config, target_fields, selected_rows)
    if target_type == "中转副表":
        return apply_selected_columns_write_transit_table(
            window,
            headers,
            rows,
            config,
            context,
            target_name,
            target_fields,
            selected_rows,
        )
    if target_type == "SQLite表":
        return apply_selected_columns_write_sqlite_table(
            window,
            headers,
            rows,
            config,
            context,
            target_name,
            target_fields,
            selected_rows,
        )
    raise ValueError(f"未知目标类型：{target_type}")


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


def export_headers_rows_to_xlsx_file(window, headers, rows, path):
    if not path:
        raise ValueError("xlsx 导出路径为空。")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    old_headers = window.app.headers
    old_rows = window.app.rows
    old_raw = window.app.raw_data
    try:
        window.app.headers = list(headers)
        window.app.rows = [list(row) for row in rows]
        window.app.raw_data = ""
        try:
            window.app.export_xlsx_with_openpyxl(path)
        except Exception:
            window.app.export_xlsx_minimal(path)
    finally:
        window.app.headers = old_headers
        window.app.rows = old_rows
        window.app.raw_data = old_raw


def sqlite_table_exists_by_name(window, table_name, context=None):
    db_path = window.get_workflow_db_path(context)
    if not db_path or not os.path.exists(db_path):
        return False
    try:
        return window.get_table_manager(context).table_exists(table_name)
    except Exception:
        return False


def apply_save_transit_memory_plan(window, context, memory_plan, headers_copy, rows_copy):
    if not memory_plan:
        return
    manager = window.check_transit_table_write_permission(
        context,
        memory_plan["table_name"],
        exists=bool(memory_plan.get("exists_before")),
        write_mode=memory_plan.get("write_mode", ""),
        fields=memory_plan.get("headers", headers_copy),
        node_type="保存中转数据",
    )
    extra = {
        "write_mode": memory_plan.get("write_mode", ""),
        "message": memory_plan.get("log_message", ""),
    }
    if memory_plan.get("operation") == "append_transit_table":
        extra["appended_rows"] = memory_plan.get("appended_rows", 0)
    context["transit_tables"][memory_plan["table_name"]] = {
        "headers": list(memory_plan.get("headers", headers_copy)),
        "rows": [list(r) for r in memory_plan.get("rows", rows_copy)],
        "source": memory_plan.get("source", "保存中转数据:覆盖"),
    }
    window.log_transit_table_event(
        manager,
        memory_plan.get("operation", "write_transit_table"),
        memory_plan["table_name"],
        memory_plan.get("headers", headers_copy),
        memory_plan.get("rows", rows_copy),
        **extra,
    )


def execute_save_transit_sqlite(window, options, headers_copy, rows_copy, context=None):
    table_raw = options.get("sqlite_table_raw", options.get("base_name", "中转数据"))
    table_name = window.app.sanitize_sql_name(table_raw, "中转数据")
    mode = options.get("sqlite_mode", "自动加时间戳")
    if mode == "覆盖同名表":
        saved_name = window.save_result_to_sqlite(headers_copy, rows_copy, table_name, overwrite=True, backup=True, context=context)
    elif mode == "追加写入":
        saved_name = save_result_to_sqlite_append(window, headers_copy, rows_copy, table_name, context=context)
    elif mode == "报错停止":
        if sqlite_table_exists_by_name(window, table_name, context=context):
            raise ValueError(f"SQLite 表已存在，按设置停止：{table_name}")
        saved_name = window.save_result_to_sqlite(headers_copy, rows_copy, table_name, overwrite=False, backup=False, context=context)
    else:
        saved_name = window.save_result_to_sqlite(headers_copy, rows_copy, table_name, overwrite=False, backup=False, context=context)
    return f"SQLite表：{saved_name}" + ("（追加写入）" if mode == "追加写入" else "")


def execute_save_transit_xlsx(window, options, headers_copy, rows_copy):
    xlsx_path = str(options.get("xlsx_path", "")).strip()
    if not xlsx_path:
        export_dir = os.path.join(get_window_app_dir(window), "export")
        xlsx_path = os.path.join(export_dir, f"{options.get('base_name', '中转数据')}.xlsx")
    export_headers_rows_to_xlsx_file(window, headers_copy, rows_copy, xlsx_path)
    return f"xlsx：{xlsx_path}"


def apply_save_transit_node_for_window(window, headers, rows, config, context=None, execute_actions=False):
    context = context if context is not None else {"transit_tables": {}}
    context.setdefault("transit_tables", {})
    result_headers, result_rows, message = apply_save_transit_node(
        headers,
        rows,
        config,
        context=context,
        execute_actions=execute_actions,
    )
    options = context.get("save_transit_options", {}) or {}
    headers_copy = context.get("save_transit_headers")
    if headers_copy is None:
        headers_copy = list(headers)
    rows_copy = context.get("save_transit_rows")
    if rows_copy is None:
        rows_copy = [list(row) for row in normalize_rows(rows, len(headers_copy))]
    saved_parts = message.split("；") if message else []

    apply_save_transit_memory_plan(window, context, context.get("save_transit_memory_plan"), headers_copy, rows_copy)
    if execute_actions and options.get("save_sqlite"):
        saved_parts.append(execute_save_transit_sqlite(window, options, headers_copy, rows_copy, context=context))
    if execute_actions and options.get("save_xlsx"):
        saved_parts.append(execute_save_transit_xlsx(window, options, headers_copy, rows_copy))
    if not saved_parts:
        saved_parts.append("未选择保存位置，仅透传数据")
    return result_headers, result_rows, "；".join(saved_parts)


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


def build_writeback_actions(window, headers, rows, config, context=None):
    table_name = str(config.get("target_table", "")).strip()
    if not table_name:
        raise ValueError("请选择目标表。")
    use_match_rules = bool(config.get("use_match_rules", True))
    match_rules = list(config.get("match_rules", []))
    mappings = list(config.get("field_mappings", []))
    if use_match_rules and not match_rules:
        raise ValueError("已启用匹配规则定位目标行，请至少添加一条匹配规则；如果想按行号顺序写入，请关闭该选项。")
    if not mappings:
        raise ValueError("请至少添加一条字段映射规则。")
    target_columns, target_records = load_target_table_rows_for_writeback(window, table_name, context=context)
    actions = build_writeback_actions_from_records(headers, rows, config, target_columns, target_records)
    return actions, table_name


def apply_external_table_to_current_node_for_window(window, headers, rows, config, context=None):
    source_table = str(config.get("source_table", "")).strip()
    if not source_table:
        raise ValueError("请选择来源表。")
    use_match_rules = bool(config.get("use_match_rules", True))
    match_rules = list(config.get("match_rules", []))
    mappings = list(config.get("field_mappings", []))
    if use_match_rules and not match_rules:
        raise ValueError("已启用匹配规则定位对应行，请至少添加一条匹配规则；如果想按行号顺序写入，请关闭该选项。")
    if not mappings:
        raise ValueError("请至少添加一条字段映射规则。")
    source_columns, source_records = load_target_table_rows_for_writeback(window, source_table, context=context)
    return apply_external_table_to_current_node(headers, rows, config, source_columns, source_records)


def apply_writeback_node_for_window(window, headers, rows, config, execute_actions=False, context=None):
    if config.get("writeback_direction", "当前表写入SQLite目标表") == "其他表写入当前表":
        return apply_external_table_to_current_node_for_window(window, headers, rows, config, context=context)

    table_name = str(config.get("target_table", "")).strip()
    if not table_name:
        raise ValueError("请选择目标表。")
    write_range_mode = config.get("write_range_mode", "局部覆盖，保留目标原行数")
    enable_write = bool(config.get("enable_write", False))
    backup_before_write = bool(config.get("backup_before_write", True))
    output_preview = bool(config.get("output_preview_table", True))

    if write_range_mode == "按来源完整结构覆盖":
        target_columns, _target_records = load_target_table_rows_for_writeback(window, table_name, context=context)
        actions, full_rows = build_writeback_full_structure_rows_for_sqlite(headers, rows, config, target_columns)
        stat = build_writeback_preview_stat(
            write_range_mode,
            actions,
            full_rows=full_rows,
            target_columns=target_columns,
        )
        if execute_actions and enable_write:
            saved = window.save_result_to_sqlite(
                target_columns,
                full_rows,
                table_name,
                overwrite=True,
                backup=backup_before_write,
                context=context,
            )
            stat = build_writeback_full_structure_execute_stat(saved, full_rows, target_columns)
        else:
            stat += get_writeback_non_execute_suffix(execute_actions, enable_write)
    else:
        actions, table_name = build_writeback_actions(window, headers, rows, config, context=context)
        action_counts = count_writeback_actions(actions)
        target_fields = get_writeback_target_fields(config)
        stat = build_writeback_preview_stat(write_range_mode, actions, target_fields=target_fields)

        if should_execute_writeback_update(execute_actions, enable_write, action_counts, write_range_mode):
            backup_name = ""
            if backup_before_write:
                backup_name = backup_sqlite_table_for_writeback(window, table_name, context=context)
            cleared = 0
            if write_range_mode == "清空目标字段后覆盖，保留目标原行数":
                result = apply_writeback_transaction_to_sqlite(
                    window,
                    table_name,
                    actions,
                    target_fields,
                    context=context,
                )
                cleared = result.get("cleared_fields", 0)
                actual = result.get("cells", 0)
            else:
                actual = (
                    apply_writeback_updates_to_sqlite(window, table_name, actions, context=context)
                    if action_counts["write_count"] > 0
                    else 0
                )
            stat = build_writeback_execute_stat(table_name, actual, cleared=cleared, backup_name=backup_name)
        else:
            stat += get_writeback_non_execute_suffix(execute_actions, enable_write)

    return finish_writeback_node_output(headers, rows, actions, stat, output_preview)
