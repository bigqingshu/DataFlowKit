# -*- coding: utf-8 -*-
"""Transit-table workflow node planning helpers."""

from core.data_utils import normalize_rows


def make_unique_transit_name(base_name, transit_tables):
    name = str(base_name or "中转数据").strip() or "中转数据"
    transit_tables = transit_tables or {}
    if name not in transit_tables:
        return name
    counter = 2
    while f"{name}_{counter}" in transit_tables:
        counter += 1
    return f"{name}_{counter}"


def append_headers_rows(old_headers, old_rows, new_headers, new_rows):
    """按字段名对齐追加 rows，字段不一致时自动取并集。"""
    old_headers = list(old_headers or [])
    new_headers = list(new_headers or [])
    merged_headers = list(old_headers)
    for header in new_headers:
        if header not in merged_headers:
            merged_headers.append(header)

    def convert_rows(src_headers, src_rows):
        index = {header: i for i, header in enumerate(src_headers)}
        converted = []
        for row in src_rows or []:
            row = list(row)
            out = []
            for header in merged_headers:
                i = index.get(header)
                if i is None or i >= len(row):
                    out.append("")
                else:
                    out.append("" if row[i] is None else str(row[i]))
            converted.append(out)
        return converted

    merged_rows = convert_rows(old_headers, old_rows) + convert_rows(new_headers, new_rows)
    return merged_headers, merged_rows


def normalize_save_transit_config(config):
    config = config or {}
    base_name = str(config.get("transit_name", "中转数据")).strip() or "中转数据"
    return {
        "base_name": base_name,
        "save_memory": bool(config.get("save_memory", True)),
        "append_memory": bool(config.get("append_memory", False)),
        "save_sqlite": bool(config.get("save_sqlite", False)),
        "save_xlsx": bool(config.get("save_xlsx", False)),
        "sqlite_table_raw": str(config.get("sqlite_table", base_name)).strip() or base_name,
        "sqlite_mode": config.get("sqlite_mode", "自动加时间戳"),
        "xlsx_path": str(config.get("xlsx_path", "")).strip(),
    }


def plan_save_transit_memory_write(headers, rows, transit_tables, options):
    transit_tables = transit_tables or {}
    base_name = options["base_name"]
    append_memory = bool(options.get("append_memory", False))
    headers_copy = list(headers)
    rows_copy = [list(row) for row in rows]
    exists_before = base_name in transit_tables
    write_mode = "追加" if append_memory else "覆盖"

    if append_memory and exists_before:
        old_item = transit_tables.get(base_name, {}) or {}
        merged_headers, merged_rows = append_headers_rows(
            old_item.get("headers", []) or [],
            old_item.get("rows", []) or [],
            headers_copy,
            rows_copy,
        )
        return {
            "operation": "append_transit_table",
            "table_name": base_name,
            "exists_before": exists_before,
            "write_mode": write_mode,
            "headers": merged_headers,
            "rows": [list(row) for row in merged_rows],
            "source": "保存中转数据:追加",
            "status": f"内存副表追加：{base_name}（新增 {len(rows_copy)} 行，累计 {len(merged_rows)} 行）",
            "log_message": f"保存中转数据追加内存副表 {base_name}：新增 {len(rows_copy)} 行，累计 {len(merged_rows)} 行",
            "appended_rows": len(rows_copy),
        }

    return {
        "operation": "write_transit_table",
        "table_name": base_name,
        "exists_before": exists_before,
        "write_mode": write_mode,
        "headers": headers_copy,
        "rows": [list(row) for row in rows_copy],
        "source": "保存中转数据:覆盖",
        "status": f"内存副表：{base_name}",
        "log_message": f"保存中转数据写入内存副表 {base_name}：{len(rows_copy)} 行 × {len(headers_copy)} 列",
        "appended_rows": 0,
    }


def build_save_transit_sqlite_preview_part(execute_actions):
    return None if execute_actions else "SQLite表：预览模式未写入"


def build_save_transit_xlsx_preview_part(execute_actions):
    return None if execute_actions else "xlsx：预览模式未导出"


def apply_save_transit_node(headers, rows, config, context=None, execute_actions=False):
    context = context if context is not None else {}
    options = normalize_save_transit_config(config)
    headers_copy = list(headers)
    rows_copy = [list(row) for row in normalize_rows(rows, len(headers_copy))]
    transit_tables = context.get("transit_tables", {}) or {}
    saved_parts = []

    memory_plan = None
    if options["save_memory"]:
        memory_plan = plan_save_transit_memory_write(headers_copy, rows_copy, transit_tables, options)
        saved_parts.append(memory_plan["status"])

    if options["save_sqlite"]:
        part = build_save_transit_sqlite_preview_part(execute_actions)
        if part:
            saved_parts.append(part)

    if options["save_xlsx"]:
        part = build_save_transit_xlsx_preview_part(execute_actions)
        if part:
            saved_parts.append(part)

    if not saved_parts and not (options["save_memory"] or options["save_sqlite"] or options["save_xlsx"]):
        saved_parts.append("未选择保存位置，仅透传数据")

    context["save_transit_options"] = options
    context["save_transit_memory_plan"] = memory_plan
    context["save_transit_headers"] = headers_copy
    context["save_transit_rows"] = rows_copy
    return list(headers), [list(row) for row in rows], "；".join(saved_parts)
