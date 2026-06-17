# -*- coding: utf-8 -*-
"""Service helpers for plugin input table reads and schema probing."""


def read_plugin_input_table_source(window, spec, current_headers, current_rows, context=None):
    """按插件节点多表配置读取一张输入表。"""
    spec = spec or {}
    context = context or {"transit_tables": {}}
    source_type = str(spec.get("source_type") or "当前工作流表").strip() or "当前工作流表"
    if source_type == "当前工作流表":
        headers = list(current_headers or [])
        rows = [list(r) for r in window.normalize_rows(current_rows or [], len(headers))]
        return {
            "type": "table",
            "headers": headers,
            "rows": rows,
            "source_name": "workflow_current",
            "meta": {"source_type": source_type},
        }
    if source_type == "SQLite表":
        table = str(spec.get("sqlite_table") or spec.get("table") or "").strip()
        if not table:
            raise ValueError("插件额外输入表未选择 SQLite 表。")
        data = window.get_table_manager(context).read_table(table)
        headers = list(data.get("headers", []))
        rows = [list(row) for row in data.get("rows", [])]
        return {
            "type": "table",
            "headers": headers,
            "rows": rows,
            "source_name": f"SQLite:{table}",
            "meta": {"source_type": source_type, "table_name": table},
        }
    if source_type == "中转副表":
        name = str(spec.get("transit_table") or spec.get("table") or "").strip()
        if not name:
            raise ValueError("插件额外输入表未选择中转副表。")
        manager = window.check_transit_table_permission(
            context,
            name,
            ["read_table"],
            operation="read_transit_table",
            field_action="read",
            node_type="插件节点",
        )
        item = (context.get("transit_tables", {}) or {}).get(name)
        if not item:
            raise ValueError(f"插件额外输入表未找到中转副表：{name}")
        headers = list(item.get("headers", []) or [])
        rows = [list(r) for r in (item.get("rows", []) or [])]
        window.log_transit_table_event(
            manager,
            "read_transit_table",
            name,
            headers,
            rows,
            message=f"读取中转副表 {name}：{len(rows)} 行 × {len(headers)} 列",
        )
        return {
            "type": "table",
            "headers": headers,
            "rows": rows,
            "source_name": f"中转:{name}",
            "meta": {"source_type": source_type, "table_name": name},
        }
    raise ValueError(f"未知插件输入表来源类型：{source_type}")


def build_plugin_input_tables(window, config, current_headers, current_rows, context=None):
    """构建插件可用的多输入表字典，兼容旧版单表 input_data。"""
    primary = window.read_plugin_input_table_source(
        {"source_type": "当前工作流表"},
        current_headers,
        current_rows,
        context,
    )
    tables = {
        "当前表": primary,
        "workflow_current": primary,
        "primary": primary,
    }
    for index, spec in enumerate(config.get("input_tables", []) or [], start=1):
        if not isinstance(spec, dict):
            continue
        if spec.get("enabled", True) is False:
            continue
        table_data = window.read_plugin_input_table_source(spec, current_headers, current_rows, context)
        alias = str(spec.get("alias") or "").strip() or f"输入表{index}"
        table_data = dict(table_data)
        meta = dict(table_data.get("meta") or {})
        meta.update({"alias": alias, "input_index": index})
        table_data["meta"] = meta
        tables[alias] = table_data
    return tables


def read_plugin_input_table_headers(window, spec, current_headers, context=None):
    """仅读取插件输入表字段，用于节点配置下拉菜单，避免 UI 阶段整表加载。"""
    spec = spec or {}
    context = context or {"transit_tables": {}}
    source_type = str(spec.get("source_type") or "当前工作流表").strip() or "当前工作流表"
    if source_type == "当前工作流表":
        return list(current_headers or [])
    if source_type == "SQLite表":
        table = str(spec.get("sqlite_table") or spec.get("table") or "").strip()
        if not table:
            return []
        return list(window.get_workflow_sqlite_columns(table, context))
    if source_type == "中转副表":
        name = str(spec.get("transit_table") or spec.get("table") or "").strip()
        item = (context.get("transit_tables", {}) or {}).get(name) if name else None
        return list((item or {}).get("headers", []) or [])
    return []


def build_plugin_input_table_headers(window, config, current_headers, context=None):
    """构建插件可用输入表的字段映射，供动态参数控件使用。"""
    table_headers = {
        "当前表": list(current_headers or []),
        "workflow_current": list(current_headers or []),
        "primary": list(current_headers or []),
    }
    for index, spec in enumerate(config.get("input_tables", []) or [], start=1):
        if not isinstance(spec, dict) or spec.get("enabled", True) is False:
            continue
        alias = str(spec.get("alias") or "").strip() or f"输入表{index}"
        try:
            table_headers[alias] = window.read_plugin_input_table_headers(spec, current_headers, context)
        except Exception:
            table_headers.setdefault(alias, [])
    return table_headers


def build_plugin_probe_input_tables(window, config, current_headers, context=None):
    """构建仅含字段的插件输入表，避免配置阶段加载整表或触发重节点。"""
    table_headers = window.build_plugin_input_table_headers(config, current_headers, context or {})
    tables = {}
    for alias, headers in (table_headers or {}).items():
        tables[alias] = {
            "type": "table",
            "headers": list(headers or []),
            "rows": [],
            "source_name": alias,
            "meta": {"lazy_schema": True, "source_type": "config_probe"},
        }
    primary = tables.get("当前表") or {
        "type": "table",
        "headers": list(current_headers or []),
        "rows": [],
        "source_name": "workflow_current",
        "meta": {"lazy_schema": True, "source_type": "config_probe"},
    }
    tables.setdefault("当前表", primary)
    tables.setdefault("workflow_current", primary)
    tables.setdefault("primary", primary)
    return tables
